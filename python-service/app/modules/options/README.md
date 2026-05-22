# Unusual Options Volume — ML Pipeline

## What This Module Does

This module detects **unusual options activity** and predicts whether that activity precedes a significant move in the underlying equity. It is the core intelligence layer of the MarketAI platform.

The module ingests raw OPRA options trade data, enriches it with derived signals (Greeks, aggressor side, sweep classification), engineers a feature vector for each contract, trains a classifier to predict whether the underlying will move more than 2% within 24 hours, and serves those predictions in real time through a FastAPI inference endpoint.

---

## Why Unusual Options Volume Matters

Options markets are where institutional traders express directional conviction when they want size, speed, or leverage that equity markets can't provide efficiently. When a large institution believes a stock is about to move — because of earnings, M&A, a regulatory event, or accumulated research — they often position in options before the move becomes visible in the underlying.

The key insight from the spec this module is built on:

> **Unusual volume alone is not predictive. The real edge comes from aggressor-side positioning, sweep behavior, IV repricing, dealer hedging pressure, opening flow, and volatility regime alignment.**

This is the central design principle. Raw contract volume tells you something happened. It doesn't tell you *what* or *why*. The features engineered in this module are designed to answer the "what" and "why" from the structure of the trade itself.

---

## The Signal Logic

### 1. Aggressor Side

Every options trade executes at some price between the bid and ask. Where it executes tells you who was motivated:

- **At the ask or above**: the buyer was aggressive — they paid up to get filled. Bullish urgency.
- **At the bid or below**: the seller was aggressive. Bearish urgency.
- **Near mid**: negotiated print, less informative.

This is inferred from `infer_aggressor()` in `services/ingest.py`:

```python
def infer_aggressor(price, bid, ask):
    if price >= ask: return "BUY"
    if price <= bid: return "SELL"
    return "MID"
```

It's a simple heuristic but grounded in market microstructure theory. The Aggressor Ratio feature (buy premium / total premium in a 5-minute window) captures whether informed buyers are systematically paying up for calls or puts.

### 2. Sweep Detection

A **sweep** is when a large order is broken across multiple exchanges and filled simultaneously, prioritizing speed over price. It looks like several trades hitting the ask on CBOE, AMEX, PHLX, and ISE within milliseconds — all the same contract, all the same side.

Sweeps are significant because they indicate the trader didn't want to tip their hand by posting a large visible order. They wanted to own the position *now*, before the market could react. This is almost always institutional behavior.

Detection logic in `services/ingest.py`:

```python
# Group by (symbol, strike, expiration, put_call, aggressor_side)
# Within a 500ms window, if trades hit ≥3 distinct exchanges on the same side → is_sweep = True
```

Sweep Intensity (sweep count / total trades in a 5-minute bucket) is one of the most predictive features in the model.

### 3. Relative Volume (RVOL)

RVOL compares today's contract volume to its 20-day rolling average:

```
RVOL = current_volume / avg_volume_20d
```

An RVOL of 10x means ten times the normal number of contracts changed hands. On its own this is noise — it could be a hedger rolling, a covered call writer, or an algorithmic strategy. Combined with aggressor side and sweep detection, elevated RVOL narrows the explanation set considerably.

### 4. Volume / Open Interest

```
Vol/OI = today's volume / existing open interest
```

When this ratio exceeds 1.0, more contracts traded today than currently exist as open positions. This strongly suggests **new position opening** rather than closing or rolling. Opening flow is more predictive than closing flow because it represents new directional conviction, not someone exiting a prior bet.

### 5. Premium Flow

```
Premium = price × 100 × contracts
```

Raw dollar value of the bet. A trader buying 100 contracts of a $2.00 premium call is spending $20,000. A sweep of 5,000 contracts at $1.50 is $750,000. Premium flow captures the economic commitment behind the activity. Small RVOL on a high-premium contract matters more than large RVOL on a $0.05 lottery ticket.

### 6. Delta Exposure

```
Delta Exposure = delta × contracts × 100
```

Delta is the options Greek measuring sensitivity to underlying price movement. Delta Exposure translates contract volume into equivalent share exposure. A trader buying 1,000 calls with delta 0.40 is effectively expressing the same directional view as buying 40,000 shares — but with far more leverage and defined risk. High aggregate delta exposure on one side indicates significant directional positioning.

### 7. IV Rank

```
IV Rank = (current_iv - iv_52w_low) / (iv_52w_high - iv_52w_low)
```

IV Rank measures where implied volatility sits relative to its past year's range. An IV Rank of 0.90 means IV is at the 90th percentile of its 52-week range — expensive options. When someone buys expensive options aggressively (high aggressor ratio, high RVOL, sweep behavior), it's a stronger signal than the same activity when IV is cheap. Paying a premium for already-expensive protection suggests strong conviction.

---

## Data Flow

```
OPRA .dbn.zst file (Databento)
        │
        ▼
services/ingest.py
  - parse raw trade records
  - enrich with Greeks (services/greeks.py → py_vollib)
  - infer aggressor side per trade
  - detect sweeps within 500ms windows
  - bulk insert → options_trades (QuestDB)
        │
        ▼
services/features.py
  - aggregate options_trades into 5-minute buckets
  - compute RVOL, Vol/OI, premium flow, sweep intensity,
    aggressor ratio, delta exposure, IV rank, days to expiry
  - write → options_features (QuestDB)
        │
        ▼
services/labels.py
  - for each options_features row, look up equity price
    24 hours later in trades_data (existing equity table)
  - label_24h = 1 if abs(future - now) / now > 0.02
  - never uses future IV, OI, or options prices (no leakage)
  - write label_24h back to options_features
        │
        ▼
ml/training/train_lgbm.py     ←── Phase 1
ml/training/train_sequence.py ←── Phase 2
  - load labeled features
  - walk-forward cross-validation (no lookahead)
  - fit SequenceNormalizer on train split only
  - train LightGBM or LSTM classifier
  - log to MLflow, export TorchScript
        │
        ▼
services/inference.py
  - load model + normalizer once via @lru_cache
  - score new contract snapshots in real time
  - rule-based fallback if no model loaded
  - top_signals(): rank recent features by signal_score
        │
        ▼
api/predictions.py
  POST /api/v1/options/predict   → single contract score
  GET  /api/v1/options/signals   → ranked top signals
```

---

## Database Schema

### `options_trades`

Stores every enriched options trade. Raw feed data plus computed fields.

| Column | Type | Description |
|---|---|---|
| `ts_event` | TIMESTAMP | Event timestamp (designated, partitioned by DAY) |
| `symbol` | SYMBOL | Underlying ticker |
| `strike` | DOUBLE | Strike price |
| `expiration` | DATE | Expiration date |
| `put_call` | SYMBOL | CALL or PUT |
| `price` | DOUBLE | Execution price (premium per share) |
| `size` | LONG | Contracts traded |
| `bid` | DOUBLE | NBBO bid at execution |
| `ask` | DOUBLE | NBBO ask at execution |
| `trade_condition` | SYMBOL | Sweep, block, etc. |
| `exchange` | SYMBOL | Execution venue |
| `iv` | DOUBLE | Implied volatility (Black-Scholes) |
| `delta` | DOUBLE | Price sensitivity to underlying |
| `gamma` | DOUBLE | Delta's sensitivity to underlying |
| `vega` | DOUBLE | Sensitivity to IV |
| `theta` | DOUBLE | Daily time decay |
| `open_interest` | LONG | Existing open contracts |
| `aggressor_side` | SYMBOL | BUY / SELL / MID (inferred) |
| `is_sweep` | BOOLEAN | Multi-exchange rapid execution |
| `premium` | DOUBLE | Total dollar value (price × 100 × size) |

### `options_features`

One row per (symbol, strike, expiration, put_call, 5-minute bucket). This is the ML input table.

| Column | Type | Description |
|---|---|---|
| `ts_event` | TIMESTAMP | Bucket timestamp |
| `symbol` | SYMBOL | Underlying ticker |
| `strike` | DOUBLE | Strike price |
| `expiration` | DATE | Expiration date |
| `put_call` | SYMBOL | CALL or PUT |
| `rvol` | DOUBLE | Relative volume vs 20-day average |
| `vol_oi_ratio` | DOUBLE | Volume / open interest |
| `premium_flow` | DOUBLE | Dollar premium in bucket |
| `sweep_intensity` | DOUBLE | Sweep fraction in bucket |
| `aggressor_ratio` | DOUBLE | Buy premium / total premium |
| `delta_exposure` | DOUBLE | Net delta × contracts × 100 |
| `iv_rank` | DOUBLE | IV percentile in 52-week range |
| `days_to_exp` | INT | Days until expiration |
| `label_24h` | INT | 1 = underlying moved >2% in 24h, 0 = no, NULL = unlabeled |

---

## ML Architecture

### Why LightGBM First

Gradient-boosted trees (LightGBM/XGBoost) consistently outperform deep learning on tabular financial datasets. They handle mixed feature scales, missing values, and non-linear interactions without requiring careful preprocessing. They're also interpretable via feature importance, which matters for understanding what the model is actually learning.

Phase 1 trains a LightGBM binary classifier with walk-forward cross-validation and logs everything to MLflow. This gives a reliable baseline and tells us which features are actually driving signal.

### Why LSTM Second

Once the LightGBM baseline is established and we understand the feature importance, the LSTM in Phase 2 adds temporal context: a sequence of 20 consecutive 5-minute feature snapshots for each contract. The hypothesis is that the *trajectory* of unusual activity matters — a sweep followed by escalating aggressor ratio followed by IV expansion is more significant than any of those signals in isolation.

Causal architecture constraints:
- No future data in any feature — all features use only information available at `ts_event`
- Labels computed from future equity prices (unavoidable — that's the prediction target), but futures prices are never in the feature vector
- Walk-forward splits: the test window is always strictly after the training window

### Training Safeguards

**Data leakage prevention**: `labels.py` only looks at `trades_data` (equity prices) for the future price, never future IV, OI, or options pricing. The labeling function is deliberately separated from feature engineering to make this boundary explicit.

**Normalizer discipline**: `SequenceNormalizer` is fit on the training split only, then applied to validation and inference. Mean and std from the future cannot influence training data normalization.

**Walk-forward splits**: `evaluation/metrics.py:walk_forward_splits()` uses expanding windows — each fold's test set is strictly after its training set. This prevents any form of look-ahead.

**Survivorship bias mitigation**: The ingestion pipeline processes whatever OPRA data you provide, including delisted symbols and expired options, as long as they are in the `.dbn.zst` file. The model trains on the data you feed it.

---

---

## Whale Positioning Detector (2–8 Week Institutional Signal)

The second major sub-feature targets a completely different behavior from the 24h flow detector: **institutional accumulation of medium-term options positions** by whales who leg in slowly over multiple days to avoid detection, committing large dollar premiums to a directional view before a major catalyst.

### How It Differs from the 24h Feature

| Dimension | 24h Unusual Volume | Whale Positioning |
|---|---|---|
| DTE filter | Any expiration | 14–60 days only |
| Aggressor filter | All sides | BUY side only |
| Time bucket | 5-minute | Daily |
| Signal type | Urgency: sweeps, immediate aggression | Accumulation: size + concentration over days |
| Premium threshold | None | ≥ $25,000 per trade |
| Label horizon | 24 hours | 28 calendar days |
| Move threshold | 2% | 5% |
| Model artifacts | `options_model.pt` | `whale_model.pkl` |
| API prefix | `/api/v1/options/*` | `/api/v1/options/whale/*` |

### Why Whales Accumulate This Way

Institutional traders with a 2-8 week directional thesis face a liquidity problem: a single large options order in a medium-liquidity contract will move the market against them. So they leg in — small lots, across multiple sessions, sometimes on multiple strikes in the same expiration — building a position before the thesis plays out.

The behavioral fingerprint of this activity:
- **Consistent buying across days** (`accumulation_days`): not a one-time event but a pattern
- **Strike concentration** (`strike_concentration`): converging on a specific strike, not scatter-gun hedging
- **Meaningful dollar commitment per trade** (`cluster_premium_total`): the $25k floor filters noise; real whales commit real money
- **Medium-duration DTE**: not 0-DTE gambling, not LEAPS hedging — 2-8 weeks is where directional conviction lives

### Whale Feature Set

| Feature | Description |
|---|---|
| `cluster_premium_total` | Total premium committed that day for this (symbol, strike, expiration, put_call) |
| `cluster_size_max` | Largest single order in the cluster |
| `cluster_trade_count` | Distinct buy trades in the daily window |
| `strike_concentration` | `1 - std(strikes) / mean(strikes)` per (symbol, day); 1.0 = all flow on one strike |
| `avg_dte` | Average days to expiration across cluster trades |
| `otm_pct` | Average out-of-the-money percentage (computed from underlying price when available) |
| `avg_delta` | Average delta of cluster; 0.3-0.5 = directional bet, not hedge |
| `premium_per_trade` | `cluster_premium_total / cluster_trade_count`; large = conviction per order |
| `vol_oi_ratio` | Cluster size / open interest; >1 = new position opening |
| `iv_rank` | IV percentile vs available history; buying into high-IV = strong conviction |
| `accumulation_days` | Distinct qualifying buy days in past 5 calendar days per contract |
| `call_put_ratio` | Call premium / total premium per (symbol, day) |

### Whale Data Flow

```
options_trades (existing table)
        │
        ▼  Filter: aggressor=BUY, DTE 14-60, premium >= $25k
        │
services/whale_features.py
  - copy filtered trades → whale_trades
  - aggregate by (symbol, strike, expiration, put_call, day)
  - compute cluster features (premium, concentration, accumulation)
  - write → whale_features (QuestDB)
        │
        ▼
services/whale_labels.py
  - look up equity price from trades_data at ts_event and +28 days
  - label_4w = 1 if abs(future - now) / now > 0.05
  - batch queries + merge_asof (no N+1, no leakage)
        │
        ▼
ml/training/train_whale_lgbm.py
  - load labeled whale_features
  - walk-forward cross-validation
  - fit SequenceNormalizer on train split only
  - save whale_model.pkl + whale_model_normalizer.pkl
        │
        ▼
services/whale_inference.py
  - @lru_cache model + normalizer loaders
  - rule-based fallback: cluster_premium * 0.5 + accumulation_days * 0.3 + concentration * 0.2
  - whale_top_signals(n, lookback_days) — queries by day, not minute
        │
        ▼
api/whale.py (mounted at /whale prefix in router.py)
  POST /api/v1/options/whale/features/compute
  POST /api/v1/options/whale/labels/generate
  POST /api/v1/options/whale/predict
  GET  /api/v1/options/whale/signals
```

### Whale Database Schema

**`whale_trades`** — filtered raw trades qualifying as potential whale activity:

| Column | Type | Description |
|---|---|---|
| `ts_event` | TIMESTAMP | Trade timestamp |
| `symbol` | SYMBOL | Underlying ticker |
| `strike`, `expiration`, `put_call` | — | Contract identity |
| `price`, `size`, `premium` | DOUBLE/LONG | Execution details |
| `delta`, `iv`, `open_interest` | DOUBLE | Greeks and OI at execution |
| `days_to_exp` | INT | DTE at trade time (14-60) |
| `otm_pct` | DOUBLE | (strike - underlying) / underlying |

**`whale_features`** — daily cluster signals per contract:

| Column | Type | Description |
|---|---|---|
| `ts_event` | TIMESTAMP | Trading day (09:30 AM) |
| `cluster_premium_total` | DOUBLE | Total $ committed that day |
| `cluster_size_max` | LONG | Largest single order |
| `cluster_trade_count` | INT | Distinct buy trades |
| `strike_concentration` | DOUBLE | Focus score [0, 1] |
| `accumulation_days` | INT | Days of buying in past 5 |
| `label_4w` | INT | 1 = >5% move in 28d, NULL = unlabeled |

### Whale API Endpoints

```
POST /api/v1/options/whale/features/compute?symbol=SPY&start_date=...&end_date=...
POST /api/v1/options/whale/labels/generate?symbol=SPY&start_date=...&end_date=...
POST /api/v1/options/whale/predict
  Body: WhaleSnapshot (symbol, strike, expiration, put_call, cluster_premium_total, ...)
  Returns: { whale_signal_score, model_loaded, scored_at, ...snapshot fields }

GET /api/v1/options/whale/signals?n=20&lookback_days=5
  Returns: { signals: [...ranked by whale_signal_score desc], count }
```

Note: `lookback_days` not `lookback_minutes` — whale signals are day-granularity.

### Training the Whale Model

```bash
# 1. Compute whale features (after ingesting OPRA data)
curl -X POST "http://localhost:8000/api/v1/options/whale/features/compute?symbol=SPY&start_date=2026-01-01&end_date=2026-05-17"

# 2. Generate 4-week labels (needs 28 days of future equity data)
curl -X POST "http://localhost:8000/api/v1/options/whale/labels/generate?symbol=SPY&start_date=2026-01-01&end_date=2026-04-20"

# 3. Train LightGBM
docker exec market_python_service python -m app.modules.options.ml.training.train_whale_lgbm --symbol SPY

# 4. Test whale signals
curl "http://localhost:8000/api/v1/options/whale/signals?n=10&lookback_days=5"
```

---

## Module Structure

```
modules/options/
├── router.py                   # Mounts all sub-routers at /api/v1/options
├── db/
│   └── schema.py               # DDL for all 4 tables (options_trades, options_features,
│                               #   whale_trades, whale_features)
├── api/
│   ├── ingest.py               # POST /ingest/upload, GET /ingest/jobs
│   ├── features.py             # POST /features/compute
│   ├── labels.py               # POST /labels/generate
│   ├── predictions.py          # POST /predict, GET /signals
│   └── whale.py                # POST /whale/features/compute, /whale/labels/generate
│                               #   POST /whale/predict, GET /whale/signals
├── services/
│   ├── greeks.py               # Black-Scholes via py_vollib
│   ├── ingest.py               # Parse, enrich, sweep-detect, bulk insert
│   ├── features.py             # 5-minute feature aggregation → options_features
│   ├── labels.py               # 24h future return labeling
│   ├── inference.py            # 24h model loader + signal ranking
│   ├── whale_features.py       # Daily whale cluster aggregation → whale_features
│   ├── whale_labels.py         # 28-day / 5% move labeling
│   └── whale_inference.py      # Whale model loader + signal ranking
└── ml/
    ├── features/
    │   ├── feature_builder.py          # Loads labeled options_features rows
    │   └── whale_feature_builder.py    # Loads labeled whale_features rows
    ├── datasets/options_dataset.py     # PyTorch Dataset + SequenceDataset
    ├── models/
    │   ├── base_model.py               # BaseFinancialModel(nn.Module)
    │   ├── lgbm_model.py               # LightGBM wrapper (24h)
    │   └── whale_model.py              # LGBMWhaleModel + WHALE_FEATURE_COLS
    ├── training/
    │   ├── train_lgbm.py               # 24h Phase 1 training
    │   ├── train_sequence.py           # 24h Phase 2 LSTM training
    │   └── train_whale_lgbm.py         # Whale Phase 1 training
    ├── evaluation/metrics.py           # Sharpe, accuracy, walk-forward splits
    └── registry/model_registry.py     # TorchScript save/load, SequenceNormalizer
```

---

## API Endpoints

All endpoints are mounted at `/api/v1/options/` in the Python service. In production, access through the NestJS gateway (`/api/v1/`) which enforces JWT authentication.

### Ingestion

```
POST /api/v1/options/ingest/upload
  Body: multipart file (.dbn.zst)
  Returns: { job_id, status, message }

GET /api/v1/options/ingest/jobs
  Returns: list of all ingestion jobs

GET /api/v1/options/ingest/jobs/{job_id}
  Returns: { id, filename, status, records_processed, error, ... }
```

### Feature Engineering

```
POST /api/v1/options/features/compute?symbol=SPY&start_date=2026-05-01&end_date=2026-05-17
  Returns: { status, rows_written, symbol }
```

Triggers aggregation of `options_trades` into `options_features`. Must be run before training.

### Label Generation

```
POST /api/v1/options/labels/generate?symbol=SPY&start_date=2026-05-01&end_date=2026-05-17
  Returns: { status, labels_written, symbol }
```

Joins `options_features` timestamps against `trades_data` to populate `label_24h`. Must be run before training.

### Inference

```
POST /api/v1/options/predict
  Body: ContractSnapshot (symbol, strike, expiration, put_call, rvol, ...)
  Returns: { signal_score, model_loaded, scored_at, ...contract fields }

GET /api/v1/options/signals?n=20&lookback_minutes=30
  Returns: { signals: [...ranked by signal_score desc], count }
```

`signal_score` is a probability in [0, 1]. A score of 0.80 means the model assigns 80% probability that the underlying will move more than 2% within 24 hours. When no trained model is loaded, a weighted rule-based fallback is used (RVOL × 0.4 + sweep_intensity × 0.3 + aggressor_ratio × 0.3).

---

## Running the Training Pipeline

```bash
# 1. Ingest OPRA data
curl -X POST http://localhost:8000/api/v1/options/ingest/upload \
  -F "file=@/path/to/opra_data.dbn.zst"

# 2. Compute features
curl -X POST "http://localhost:8000/api/v1/options/features/compute?symbol=SPY&start_date=2026-01-01&end_date=2026-05-17"

# 3. Generate labels
curl -X POST "http://localhost:8000/api/v1/options/labels/generate?symbol=SPY&start_date=2026-01-01&end_date=2026-05-17"

# 4. Train LightGBM baseline (Phase 1)
docker exec market_python_service python -m app.modules.options.ml.training.train_lgbm --symbol SPY

# 5. (Optional) Train LSTM sequence model (Phase 2)
docker exec market_python_service python -m app.modules.options.ml.training.train_sequence --symbol SPY --window 20

# 6. View MLflow runs
open http://localhost:5000

# 7. Test inference
curl -X POST http://localhost:8000/api/v1/options/predict \
  -H "Content-Type: application/json" \
  -d '{"symbol":"SPY","strike":500,"expiration":"2026-06-20","put_call":"CALL","rvol":8.5,"sweep_intensity":0.7,"aggressor_ratio":0.85,"delta_exposure":42000,"iv_rank":0.72,"days_to_exp":34}'
```

---

## Known Limitations and Future Work

**Greeks enrichment in ingestion**: The current implementation computes Greeks using the trade price as the underlying price approximation. In production this should use a live underlying price feed (from `trades_data` or a separate equity tick feed) at the moment of each trade to compute accurate IV and delta.

**Open interest**: OPRA trade data does not include real-time OI. The `open_interest` field is populated from instrument definition records in the Databento feed when available. A separate daily OI snapshot ingestion should be added for more reliable Vol/OI ratios.

**Kafka/streaming**: The current architecture is batch-based — files are uploaded, processed, and features are computed on demand. A streaming architecture (Redpanda/Kafka) would allow real-time feature computation as trades arrive, which is necessary for the <500ms latency target in a live trading environment.

**Cross-asset regime**: The spec calls for market regime conditioning (VIX, SPY, QQQ, interest rates). These are not yet included as features. A high-VIX regime changes what "unusual" means — RVOL of 3x is more significant in a low-volatility regime than in a panic.

**Dealer gamma exposure**: Aggregate dealer gamma positioning (GEX) is one of the most powerful contextual signals for predicting pinning behavior and volatility events, but requires modeling the market maker hedging book across the entire options chain, not just individual trades.
