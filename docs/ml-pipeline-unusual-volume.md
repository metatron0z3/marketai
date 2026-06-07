# ML Pipeline — Unusual Options Volume (TOS Data)

**Objective:** Turn raw unusual options volume events from the TOS MCP server into
high-conviction directional signals with quantified expected value.

**Philosophy:** Unusual options volume is a noisy signal. The ML job is not to
filter noise — it's to learn which *kinds* of unusual volume are actually informed.
A sweep on a high-IV-rank, OTM weekly call in a strong-momentum stock 3 weeks before
earnings is very different from the same volume pattern in a choppy, mean-reverting
large-cap. The models learn these distinctions from labeled history.

---

## Data Sources (from TOS MCP Server)

```
tos-questdb:  options_unusual_volume_events  ← primary signal events
              options_chain_snapshots         ← context at time of event
              iv_surface_snapshots            ← vol regime features
              underlying_intraday_bars        ← price momentum features
              ticker_daily_summary            ← daily aggregated context

tos-postgres: signal_catalog                 ← labeled training data
              signal_clusters                ← multi-strike aggregates
              earnings_calendar              ← event proximity feature
              watchlist                      ← active symbol universe
```

---

## Feature Engineering

### Module: `python-service/app/modules/options/ml/features/tos_feature_builder.py`

```python
# Full feature set for one unusual_volume_event row

CONTRACT_FEATURES = [
    # Volume signal strength
    "volume_ratio_10d",         # current vol / 10d avg
    "volume_ratio_20d",         # current vol / 20d avg — primary signal
    "vol_oi_ratio",             # volume / open_interest (>1 = new positions opening)
    "premium_total",            # notional premium: mark * volume * 100
    "log_premium_total",        # log-scaled premium
    
    # Contract geometry
    "otm_pct",                  # how far OTM (0 = ATM, positive = OTM)
    "days_to_expiry",           # DTE
    "dte_bucket",               # categorical: weekly(0-7), biweekly(8-14),
                                #              monthly(15-30), quarterly(31-90)
    "is_call",                  # 1 for call, 0 for put
    
    # Greeks (directional and convexity)
    "delta_abs",                # |delta| — 0=far OTM, 0.5=ATM, 1=deep ITM
    "gamma",                    # convexity (high near ATM expiry)
    "theta_per_day",            # daily decay cost
    "vega",                     # sensitivity to IV moves
    "theta_vega_ratio",         # cost of carry vs vol sensitivity
    
    # Pricing and liquidity
    "ba_spread_pct",            # (ask-bid)/mark — wide = illiquid
    "iv_at_event",              # implied vol of this contract
    "iv_vs_hv_ratio",           # this contract's IV / underlying 20d HV
    
    # Session
    "hour_of_day",              # 9=open, 15=power hour
    "is_morning",               # first 90 minutes (more informed)
    "is_afternoon",             # last 90 minutes (gamma hedging activity)
]

UNDERLYING_CONTEXT_FEATURES = [
    # Momentum
    "underlying_return_1d",     # today's move so far
    "underlying_return_5d",     # prior week return
    "underlying_return_20d",    # prior month return
    "underlying_rsi_14",        # RSI at time of event
    "underlying_vol_ratio_20d", # stock volume vs 20d avg (is stock itself active?)
    
    # Volatility regime
    "iv_rank",                  # 0-100 (high = vol is expensive, premium selling favored)
    "iv_percentile",            # alternative to IVR
    "iv_hv_ratio",              # IV / 20d HV (>1 = IV premium over realized)
    "atm_iv",                   # absolute ATM IV level
    "skew_25d",                 # put skew (high = market expects downside)
    "term_slope",               # IV term structure slope (backwardation = stress)
    "iv_change_1d",             # IV rank change from yesterday (expanding vs contracting)
    
    # Options flow context
    "put_call_ratio_1d",        # today's PCR so far (sentiment)
    "unusual_events_count_1d",  # how many other unusual events today (confirmation)
    "unusual_events_count_5d",  # cumulative smart money activity this week
    "call_bias_today",          # (call unusual events - put unusual events) / total
    
    # Event calendar
    "days_to_earnings",         # distance to next earnings (negative = post-earnings)
    "is_within_2w_earnings",    # binary: within 14 days of earnings
    "is_post_earnings",         # binary: within 5 days after earnings
    
    # Market regime
    "vix_level",                # VIX at time of event
    "spy_return_5d",            # SPY momentum (market trend)
    "spy_return_20d",           # broader market context
    "vix_percentile_60d",       # VIX regime: low(calm)/mid/high(fear)
]

CLUSTER_FEATURES = [
    # Multi-strike context (from signal_clusters, 0 if isolated event)
    "cluster_contract_count",   # how many strikes fired together
    "cluster_call_put_ratio",   # call/put premium split (directional conviction)
    "cluster_total_premium",    # total premium across cluster
    "cluster_strike_dispersion",# std(strikes)/atm — tight=conviction, wide=hedging
    "cluster_dte_range",        # max_dte - min_dte in cluster
    "cluster_weighted_delta",   # portfolio delta implied by cluster
    "is_isolated_event",        # 1 if no cluster (single contract, weaker)
]

HISTORICAL_TICKER_FEATURES = [
    # How has this ticker responded to past unusual volume?
    "ticker_signal_hit_rate_30d",  # % of past signals that were directionally correct
    "ticker_signal_count_30d",     # how many past signals (recurring activity)
    "ticker_avg_return_5d_after",  # average 5d return following unusual vol
    "ticker_avg_premium_30d",      # typical unusual event size for this name
]

ALL_FEATURES = (
    CONTRACT_FEATURES
    + UNDERLYING_CONTEXT_FEATURES
    + CLUSTER_FEATURES
    + HISTORICAL_TICKER_FEATURES
)
```

---

## Labels

All labels attach to each signal in `signal_catalog` via the nightly follow-through job.

```python
# Computed by EOD job, T+1 through T+10

LABEL_DEFINITIONS = {
    # Primary classification targets
    "direction_correct_5d": lambda row: (
        (row.option_type == "C" and row.underlying_return_5d_fwd > 0)
        or (row.option_type == "P" and row.underlying_return_5d_fwd < 0)
    ),
    "move_exceeded_2pct_5d": lambda row: abs(row.underlying_return_5d_fwd) > 0.02,
    "quality_signal": lambda row: (           # composite: correct AND moved enough
        row.direction_correct_5d
        and row.move_exceeded_2pct_5d
    ),
    
    # Regression targets
    "underlying_return_5d_fwd":  "float",     # raw return
    "underlying_return_10d_fwd": "float",
    "mfe_5d": "float",                        # max favorable excursion in 5 days
    "mae_5d": "float",                        # max adverse excursion
    "option_return_5d": "float",              # option mark return if held
    
    # Timing targets
    "days_to_peak": "int",                    # how many days to MFE (survival analysis)
    "realized_within_2d": "bool",             # quick mover vs slow burn
}
```

---

## Models

### Model 1: Signal Quality Classifier (primary model)

**Question:** Is this unusual volume event informed, or noise?

```python
# python-service/app/modules/options/ml/models/signal_quality_model.py

# Architecture: LightGBM with SHAP explanations
# Target: quality_signal (directionally correct AND move > 2%)
# This is a binary classification problem with class imbalance (few quality signals)

import lightgbm as lgb

LGBM_PARAMS = {
    "objective": "binary",
    "metric": ["auc", "binary_logloss"],
    "learning_rate": 0.05,
    "num_leaves": 63,
    "max_depth": 6,
    "min_child_samples": 50,      # prevent overfitting to rare events
    "scale_pos_weight": 3,        # upweight positive class (quality signals ~25%)
    "subsample": 0.8,
    "colsample_bytree": 0.7,
    "reg_alpha": 0.1,
    "reg_lambda": 1.0,
    "n_estimators": 500,
    "early_stopping_rounds": 50,
}

# Key evaluation metrics:
#   - AUC (ranking ability)
#   - Precision at top decile (are the top-scored signals actually good?)
#   - Lift curve (vs random baseline)
```

### Model 2: Direction Predictor

**Question:** Given unusual volume, which direction will the underlying move?

```python
# python-service/app/modules/options/ml/models/direction_model.py

# Architecture: XGBoost with asymmetric cost
# Target: underlying_return_5d_fwd > 0 (1 = up, 0 = down/flat)
# Important: train SEPARATELY for calls and puts
#   Call model: predict "will underlying go up?"
#   Put model: predict "will underlying go down?"
# The option type itself is prior info; this model confirms/contradicts it

import xgboost as xgb

XGB_PARAMS = {
    "objective": "binary:logistic",
    "eval_metric": "auc",
    "eta": 0.05,
    "max_depth": 5,
    "min_child_weight": 30,
    "subsample": 0.8,
    "colsample_bytree": 0.7,
    "scale_pos_weight": 1.2,      # slight upweight for bull signals (market drifts up)
}

# Features: underlying_context + cluster_features (NOT contract geometry)
# Rationale: direction depends on macro context, not DTE or strike
```

### Model 3: Magnitude Estimator

**Question:** How big will the move be?

```python
# python-service/app/modules/options/ml/models/magnitude_model.py

# Architecture: LightGBM quantile regression
# Target: underlying_return_5d_fwd (continuous)
# Train three quantile heads: q10, q50, q90
# Output: (expected_return, low_bound, high_bound) — gives a distribution

from lightgbm import LGBMRegressor

QUANTILES = [0.10, 0.50, 0.90]

def train_quantile_model(X_train, y_train, alpha):
    return LGBMRegressor(
        objective="quantile",
        alpha=alpha,
        n_estimators=300,
        learning_rate=0.05,
        num_leaves=31,
        min_child_samples=50,
    ).fit(X_train, y_train)

# Also compute: probability_of_mfe_exceeding_threshold
# i.e. "probability that the underlying moves > 2% in the right direction within 5d"
# This is more actionable than raw return prediction
```

### Model 4: Regime Classifier

**Question:** What market regime are we in right now?

```python
# python-service/app/modules/options/ml/models/regime_model.py

# Architecture: Unsupervised clustering → supervised assignment
# Regimes (to discover via K-means/GMM, then label):
#   - "Trending Bull": low VIX, SPY momentum positive, IV contracting
#   - "Trending Bear": elevated VIX, SPY momentum negative, put skew high
#   - "Choppy/Range": low vol, mean-reverting, gamma scalp environment
#   - "Vol Expansion": VIX rising fast, term structure inverting
#   - "Post-Shock Recovery": VIX spike then fade, oversold bounce

# Regime features:
REGIME_FEATURES = [
    "vix_level", "vix_1w_change", "vix_percentile_60d",
    "spy_return_5d", "spy_return_20d",
    "spy_rsi_14", "spy_volume_ratio_20d",
    "average_iv_rank_watchlist",   # mean IV rank across all watchlist symbols
    "average_skew_watchlist",      # mean put skew
    "term_slope_spy",              # VIX term structure
]

# Once regime is assigned at inference time, condition all other model predictions:
# signal_score_adjusted = signal_score * regime_multipliers[current_regime]
# Trending regimes amplify directional signals; choppy regimes discount them
```

### Model 5: Multi-Strike Event Aggregator (Attention Model)

**Question:** When multiple contracts fire together, what does the aggregate pattern say?

```python
# python-service/app/modules/options/ml/models/cluster_aggregator.py

# Architecture: Simple attention-weighted aggregation
# Input: set of N contract feature vectors in same cluster
# Output: single composite signal vector passed to signal_quality_model

import torch
import torch.nn as nn

class ClusterAggregator(nn.Module):
    """
    Attention-based aggregation of multi-strike unusual volume clusters.
    Learns which contracts in a cluster carry the most informative signal.
    """
    def __init__(self, feature_dim: int = 20, hidden_dim: int = 64):
        super().__init__()
        self.attention = nn.Sequential(
            nn.Linear(feature_dim, hidden_dim),
            nn.Tanh(),
            nn.Linear(hidden_dim, 1),
        )
        self.encoder = nn.Linear(feature_dim, hidden_dim)
    
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: (batch, n_contracts, feature_dim)
        weights = torch.softmax(self.attention(x).squeeze(-1), dim=-1)
        # weights: (batch, n_contracts) — which contracts are most informative?
        encoded = self.encoder(x)              # (batch, n_contracts, hidden_dim)
        aggregate = (weights.unsqueeze(-1) * encoded).sum(dim=1)  # (batch, hidden_dim)
        return aggregate, weights

# Training: supervised with cluster-level labels from signal_clusters
# The model learns: "OTM short-dated sweeps dominate; far-OTM longs are noise"
```

### Model 6: Event Sequence Transformer

**Question:** Does the *pattern* of unusual volume events over the prior 5 days predict
a move — even if today's isolated event looks ordinary?

```python
# python-service/app/modules/options/ml/models/sequence_model.py

# Architecture: Compact Transformer (6 heads, 4 layers) — not GPT-scale
# Input: sequence of last N=10 unusual volume events for a ticker (padded)
# Each event is a feature vector (contract + context features)
# Output: (quality_score, direction_score)
# 
# Key insight: a single unusual event is weak; the same ticker lighting up
# repeatedly over 3-5 days with increasing premium is very strong.
# This model captures the temporal accumulation pattern.

import torch
import torch.nn as nn

class EventSequenceTransformer(nn.Module):
    def __init__(
        self,
        input_dim: int = 40,
        d_model: int = 128,
        nhead: int = 4,
        num_layers: int = 3,
        dropout: float = 0.1,
    ):
        super().__init__()
        self.input_proj = nn.Linear(input_dim, d_model)
        self.pos_encoding = nn.Embedding(20, d_model)  # positional (by day)
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model, nhead=nhead, dropout=dropout, batch_first=True
        )
        self.transformer = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)
        self.classifier = nn.Sequential(
            nn.Linear(d_model, 64),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(64, 2),   # [quality_score, direction_logit]
        )
    
    def forward(self, events: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
        # events: (batch, seq_len, input_dim)
        x = self.input_proj(events)
        positions = torch.arange(events.size(1), device=events.device)
        x = x + self.pos_encoding(positions)
        x = self.transformer(x, src_key_padding_mask=mask)
        cls_repr = x[:, -1, :]   # use last (most recent) event as aggregate
        return self.classifier(cls_repr)

# Training data construction:
#   For each signal in signal_catalog with quality label:
#   X = last 10 unusual_volume_events for same symbol (padded if fewer)
#   y = (quality_signal, direction_correct_5d)
#
# This model becomes the strongest single model once you have ~3 months of data.
```

---

## Training Pipeline

### Walk-Forward Cross-Validation (no data leakage)

```python
# python-service/app/modules/options/ml/training/train_tos_models.py

# CRITICAL: options data has strong temporal autocorrelation.
# Standard k-fold will leak future into past. Use expanding-window CV only.

def walk_forward_cv(df, n_splits=5, min_train_months=3):
    """
    Split: train on months 1..N, validate on month N+1.
    Slide forward. Never use future data to train.
    """
    df = df.sort_values("detected_at")
    months = df["detected_at"].dt.to_period("M").unique()
    
    for i in range(min_train_months, len(months) - 1):
        train_cutoff = months[i].to_timestamp(how="end")
        val_start    = months[i].to_timestamp(how="start")
        val_end      = months[i + 1].to_timestamp(how="end")
        
        X_train = df[df.detected_at <= train_cutoff][ALL_FEATURES]
        y_train = df[df.detected_at <= train_cutoff]["quality_signal"]
        X_val   = df[(df.detected_at >= val_start) & (df.detected_at <= val_end)][ALL_FEATURES]
        y_val   = df[(df.detected_at >= val_start) & (df.detected_at <= val_end)]["quality_signal"]
        
        yield X_train, y_train, X_val, y_val

# Evaluation metrics per fold:
#   - AUC
#   - Precision at top decile (most important — top-scored signals should be best)
#   - Lift at top quintile
#   - Calibration (is score=0.7 actually right 70% of the time?)
```

### Training Schedule

```python
# Triggered by: new day's follow-through data arriving (T+5 labels now complete)
# Run nightly at 9pm ET, Mon-Fri

async def nightly_model_refresh():
    df = load_signal_catalog_with_labels(
        min_labeled_days=5,       # only rows where 5d follow-through is filled
        min_training_rows=500,    # don't retrain until we have enough data
    )
    
    # 1. Retrain signal quality model (lightweight, <60s)
    train_lgbm_signal_quality(df)
    
    # 2. Retrain direction models (call + put separately)
    train_xgb_direction(df[df.option_type == "C"], label="call")
    train_xgb_direction(df[df.option_type == "P"], label="put")
    
    # 3. Retrain magnitude estimator (quantile regression)
    train_lgbm_magnitude(df)
    
    # 4. Sequence model — retrain weekly (more expensive)
    if is_sunday():
        train_sequence_transformer(df)
    
    # 5. Update model registry + promote if val AUC improves
    promote_if_better(metric="auc", threshold=0.01)
```

---

## Novel Research Angles

### Research 1: Causal Discovery — Does Unusual Volume Lead or Lag?

```python
# Granger causality test: does options volume predict stock returns
# or do stock moves trigger options activity?
# Answer shapes how we use the signal (leading indicator vs confirming indicator)

from statsmodels.tsa.stattools import grangercausalitytests

def test_options_volume_causality(symbol: str, lag_days: int = 5):
    df = load_daily_series(symbol)  # (date, unusual_vol_count, underlying_return)
    result = grangercausalitytests(df[["unusual_vol_count", "underlying_return"]], maxlag=lag_days)
    return extract_p_values(result)
    # Hypothesis: unusual_vol_count at T Granger-causes underlying_return at T+1..T+5
    # If p < 0.05: options flow leads price → use as leading indicator
    # If p > 0.05: price leads options → use as confirmation only
```

### Research 2: Smart Money Fingerprinting

```python
# Hypothesis: certain recurring patterns of unusual volume are left by the same
# institutional actor. Can we cluster these "fingerprints" and track them over time?

# Features for clustering:
FINGERPRINT_FEATURES = [
    "time_of_day_bucket",    # 9:30-10:30am, 10:30-12pm, etc.
    "otm_pct_bucket",        # deep OTM / moderate OTM / near ATM
    "dte_bucket",            # weekly / monthly / quarterly
    "premium_size_bucket",   # small / medium / large / whale
    "is_sweep",
    "iv_rank_bucket",        # low / mid / high IV environment
]

# Cluster unusual volume events (HDBSCAN — handles noise well)
# Track cluster membership over time
# Hypothesis: some clusters have consistently higher hit rates than others
# (the "smart" clusters)
```

### Research 3: Cross-Asset Contagion Detection

```python
# When ETF options (SPY, QQQ, XLK, XLE) show unusual volume,
# do same-sector single stocks see follow-through?
# This creates a sector-rotation signal from ETF options flow

# Implementation:
# 1. Detect unusual volume in ETFs
# 2. Look up sector membership of ETF
# 3. Check if single stocks in that sector ALSO saw unusual volume same day
# 4. Joint signal: ETF + same-sector single stock = high conviction
# 5. Lone ETF unusual volume = sector-level, weaker for individual names

SECTOR_ETF_MAP = {
    "XLK": ["AAPL", "MSFT", "NVDA", "AVGO", "AMD"],
    "XLF": ["JPM", "BAC", "GS", "MS", "WFC"],
    "XLE": ["XOM", "CVX", "COP", "SLB"],
    "XLV": ["LLY", "UNH", "JNJ", "MRK", "ABBV"],
    # ...
}
```

### Research 4: Gamma Squeeze Setup Detector

```python
# When OI concentrates at a strike near current price, MMs must delta-hedge.
# If underlying moves through that strike, MMs must buy more → self-reinforcing move.
# Classic gamma squeeze setup.

# Detection:
def detect_gamma_squeeze_setup(chain_snapshot):
    atm_strike = find_atm_strike(chain_snapshot.underlying_price)
    atm_call_oi = chain_snapshot.loc[atm_strike, "C"]["open_interest"]
    
    # Key indicator: call OI at ATM > 3x average OI at that strike over last 30d
    # AND short-dated (weekly expiry)
    # AND IV expanding (MMs pricing in the move)
    
    oi_ratio = atm_call_oi / baseline.avg_oi_30d
    is_weekly = chain_snapshot.days_to_expiry <= 7
    iv_expanding = chain_snapshot.iv_change_1d > 0.05
    
    return oi_ratio > 3.0 and is_weekly and iv_expanding
```

### Research 5: Earnings Anticipation vs Post-Earnings Fading

```python
# Two very different regimes:
# Pre-earnings (T-14 to T-1): smart money positioning → signal likely real
# Post-earnings (T+1 to T+5): vol crush, repositioning → signal often noise
# Model should have separate heads for pre/post earnings

# Implementation: add "earnings_regime" as a categorical feature
# [far_from_earnings, approaching_earnings, post_earnings_week]
# Train conditional models or include regime interaction features
```

### Research 6: Conviction Score Composite

```python
# Final output: a single conviction score [0,1] per unusual volume event
# Interpretable: "How confident are we this is informed flow?"

def compute_conviction_score(event, models, regime):
    quality_score    = models["quality"].predict_proba(event.features)[1]
    direction_score  = models["direction"][event.option_type].predict_proba(event.features)[1]
    magnitude_q90    = models["magnitude"][0.90].predict(event.features)
    regime_mult      = REGIME_MULTIPLIERS[regime]
    
    # Weighted geometric mean (all signals must be good for high conviction)
    raw_score = (quality_score ** 0.5) * (direction_score ** 0.3) * (min(magnitude_q90 / 0.05, 1) ** 0.2)
    return raw_score * regime_mult

REGIME_MULTIPLIERS = {
    "trending_bull": 1.1,
    "trending_bear": 1.1,
    "choppy_range":  0.7,    # discount all signals in choppy market
    "vol_expansion": 1.3,    # vol expansion amplifies options signals
    "post_shock":    0.9,
}
```

---

## New MarketAI Python Modules

```
python-service/app/modules/
└── tos/
    ├── __init__.py
    ├── router.py                        # FastAPI router: /api/v1/tos/*
    ├── db/
    │   ├── tos_db.py                    # QuestDB + Postgres connections to TOS MCP server
    │   └── schema.py                    # (read-only; TOS server owns schema creation)
    ├── api/
    │   ├── signals.py                   # GET /signals (unusual volume events)
    │   ├── chain.py                     # GET /chain (snapshots)
    │   └── score.py                     # POST /score (run ML inference on event)
    ├── ml/
    │   ├── features/
    │   │   └── tos_feature_builder.py   # extract ALL_FEATURES from raw event
    │   ├── models/
    │   │   ├── signal_quality_model.py  # LightGBM binary classifier
    │   │   ├── direction_model.py       # XGBoost call/put direction models
    │   │   ├── magnitude_model.py       # quantile regression
    │   │   ├── regime_model.py          # market regime classifier
    │   │   ├── cluster_aggregator.py    # attention-based multi-strike aggregator
    │   │   └── sequence_model.py        # Transformer on event sequence
    │   ├── training/
    │   │   ├── train_signal_quality.py
    │   │   ├── train_direction.py
    │   │   ├── train_magnitude.py
    │   │   ├── train_sequence.py
    │   │   └── walk_forward_cv.py       # shared CV framework
    │   ├── research/
    │   │   ├── granger_causality.py     # Research 1
    │   │   ├── fingerprint_clustering.py # Research 2
    │   │   ├── sector_contagion.py      # Research 3
    │   │   ├── gamma_squeeze_detect.py  # Research 4
    │   │   └── earnings_regime.py       # Research 5
    │   └── inference/
    │       ├── conviction_scorer.py     # final composite score
    │       └── batch_score_signals.py   # nightly batch scoring of new events
    └── flows/
        ├── nightly_retrain_flow.py      # Prefect: fetch labels → retrain → promote
        └── signal_scoring_flow.py       # Prefect: score new signals → write back
```

---

## New NestJS Modules

```
backend-nest/src/modules/
└── tos-signals/
    ├── tos-signals.module.ts
    ├── tos-signals.controller.ts   # GET /api/v1/tos/signals
    ├── tos-signals.service.ts      # proxy to Python /api/v1/tos/*
    └── dto/
        ├── tos-signal.dto.ts
        └── conviction-score.dto.ts
```

---

## Angular Frontend Additions

### Signals Dashboard (new page: `/signals`)

- **Signal Feed:** real-time list of unusual volume events scored by conviction
- **Filters:** ticker, min conviction, call/put, DTE range, premium range
- **Cluster View:** group concurrent multi-strike events into a single card
- **Signal Timeline:** sparkline of unusual events per ticker over 5 days
- **Conviction Badge:** color-coded score (0.0-0.4 gray, 0.4-0.7 yellow, 0.7+ green)

### Chart Overlay

- Unusual volume event markers on the underlying price chart
- Colored dots at the time of detection, sized by premium
- Click opens event detail: contract, volume ratio, conviction score, Greeks

---

## Evaluation Framework

```python
# Core metrics — tracked per model version in model_registry

EVAL_METRICS = {
    # Classification
    "auc":                  "primary ranking metric",
    "precision_top_decile": "what % of top-scored signals are correct?",
    "lift_top_quintile":    "vs random baseline",
    "calibration_ece":      "expected calibration error (is score a real probability?)",
    
    # Financial
    "direction_accuracy":         "% of signals where direction was correct",
    "avg_return_top_quartile":    "mean 5d return of signals with score > 0.75",
    "avg_return_bottom_quartile": "mean 5d return of signals with score < 0.25",
    "separation_ratio":           "top / bottom quartile return (want >> 1)",
    
    # Regime-conditional
    "auc_by_regime":        "AUC per market regime (model shouldn't degrade in any regime)",
    "auc_pre_earnings":     "AUC for signals within 14d of earnings",
    "auc_post_earnings":    "AUC for post-earnings signals",
}

# Target thresholds for promotion:
PROMOTION_CRITERIA = {
    "auc": 0.60,                # > random (0.5), reasonable for this signal type
    "precision_top_decile": 0.45,  # top 10% of signals right ~45%+ of the time
    "direction_accuracy": 0.58,    # better than 50% coin flip
}
```

---

## Implementation Sequence

**Phase A — Data Foundation (weeks 1-2, in MarketAI once TOS server is live)**
1. Add TOS QuestDB/Postgres connection config to `core/db.py`
2. Build `tos_feature_builder.py` — all features from raw events
3. Build the follow-through loader — pull from `signal_catalog`
4. Validate feature pipeline end-to-end with first real data

**Phase B — Baseline Models (weeks 3-4)**
5. Train signal quality classifier (LightGBM) with walk-forward CV
6. Train direction models (call + put)
7. Build conviction scorer combining both
8. Wire inference through new `tos-signals` NestJS module

**Phase C — Advanced Models (weeks 5-8)**
9. Multi-strike cluster aggregator (attention model)
10. Event sequence Transformer
11. Regime classifier
12. Magnitude estimator with quantile heads

**Phase D — Research (ongoing)**
13. Granger causality analysis per ticker
14. Smart money fingerprint clustering
15. Gamma squeeze setup detector
16. Sector contagion model
