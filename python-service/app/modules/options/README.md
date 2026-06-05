# Unusual Options Volume — ML Pipeline

## What This Module Does

This module detects **unusual options activity** and predicts whether that activity precedes a significant move in the underlying equity. It is the core intelligence layer of the MarketAI platform.

The module supports two independent data source paths — **Databento** (tick-level OPRA trade data) and **Massive API** (OHLCV aggregate bars) — which feed the same ML pipeline via a `data_source` parameter. Both paths coexist: Databento data is not replaced, deprecated, or removed. Databento remains the higher-fidelity path; Massive enables broader historical coverage at lower cost.

---

## Data Sources

### Overview

| Property | Databento (OPRA) | Massive API |
|---|---|---|
| Feed type | Tick-level trade records | OHLCV aggregate bars |
| Granularity | Individual trades with bid/ask/exchange | Minute/daily bars |
| Greeks | Yes — IV, delta, gamma, vega, theta | No |
| Aggressor side | Yes — inferred from bid/ask spread | No |
| Sweep detection | Yes — multi-exchange within 500ms | No |
| Open interest | Yes — from instrument definition records | No |
| Options table | `options_trades` | `options_bars` |
| Equity table | `trades_data` | `underlying_bars` |
| Contract metadata | Embedded in feed | `options_contracts` |
| Run tracking | Not tracked | `options_ingest_runs` |
| Cost | Per-GB data purchase | Free tier (~5 req/min) |
| Best for | Full signal fidelity; sweep/aggressor training | Broad symbol coverage; historical OHLCV |

### When to Use Each Path

**Use Databento when:**
- You have `.dbn.zst` OPRA files and need the full feature set (aggressor ratio, sweep intensity, IV rank, delta exposure)
- Training a model where signal quality matters more than data breadth
- Backtesting sweep-based or aggressor-based strategies

**Use Massive when:**
- You need longer historical windows or more symbols than available OPRA files cover
- Training a model on RVOL + premium flow + DTE features only
- Running the pipeline in an environment where Databento data is not available

**Training note:** A model trained on Databento features (sweep_intensity > 0, aggressor_ratio > 0) should not be served against Massive features (those fields zero-filled). Feature distribution mismatch will degrade signal quality. Train and serve with the same `data_source`.

### Table Naming Convention

Raw ingested tables are source-prefixed to make lineage self-documenting:

| Prefix | Source | Tables |
|---|---|---|
| *(none)* | Databento / derived | `options_trades`, `options_features`, `whale_trades`, `whale_features` |
| `msv_` | Massive API | `msv_options_bars`, `msv_underlying_bars`, `msv_options_contracts`, `msv_ingest_runs` |
| `yf_` | yfinance | `yf_ohlcv_daily` |
| `dbto_` | Databento (raw tick) | `dbto_tbbo` (reserved for future rename) |

> **Note:** The current Massive tables (`options_bars`, `options_bars`, `options_contracts`, `options_ingest_runs`) are pending rename to the `msv_` prefix. The rename requires a CREATE→INSERT→DROP migration because QuestDB has no ALTER TABLE RENAME. Until that rename is done, the code references the old table names.

---

## Ingestion Modes

The pipeline operates in two fundamentally different modes. Understanding which mode you're in changes what you run, what you check, and what "done" means.

### Mode 1 — Historical Baseline Acquisition

**What it is**: A deliberate, bounded backfill of a defined date range and symbol set. Run once (or a small number of times) to build a training corpus large enough to be statistically meaningful. This is a background process that may take days or weeks.

**When you're in it**:
- You're adding a symbol, a new quarter, or a new data type for the first time
- The `options_ingest_runs` table has gaps (missing quarters, error status, partial bar counts)
- A new data source type has been identified and needs a year+ of history before it's usable for training

**What "done" means**: Every `{symbol, quarter, contract_type}` tuple in the target coverage matrix has `status = completed` in `options_ingest_runs` AND a bar-count sanity check passes. "Complete" is a defined assertion, not a feeling.

**Gap detection query**:
```sql
-- See what's missing or failed
SELECT underlying_symbol, start_date, end_date, contract_type,
       status, contracts_ingested, bars_written
FROM options_ingest_runs
ORDER BY underlying_symbol, start_date;

-- Check actual bar coverage per symbol/month
SELECT underlying_symbol, contract_type,
       dateadd('month', 0, ts_event) as month,
       count() as bars
FROM options_bars
WHERE underlying_symbol IN ('TSLA', 'NVDA', 'AAPL', 'AMD', 'META')
SAMPLE BY 1M ALIGN TO CALENDAR
ORDER BY underlying_symbol, month;
```

**Rate-limit patience**: On the Massive free plan (~5 req/min), acquiring one full year of daily bars for one symbol across all contracts takes approximately 2–4 hours per quarter. A 5-symbol × 5-quarter × 2 contract-type target (~50 runs) is a multi-day background job. This is expected and acceptable. Use `nohup` + log file, or Prefect flows with automatic retry.

**This pattern is generic**: Every time a new data type is identified — earnings transcripts, macro indicators, analyst sentiment, alternative data feeds — we will enter historical baseline acquisition mode for that type. The same principles apply regardless of what the data is:

1. Define the coverage target: `{what symbols} × {what date range} × {what data type}`
2. Write an idempotent ingest service with a **run tracking table** (same pattern as `options_ingest_runs`)
3. Verify completeness via gap detection against both the run table and the actual data table
4. Declare the historical baseline complete only after gap detection passes
5. Only then use the data for feature engineering and training

The pipeline should never treat a partial historical dataset as complete. Training on an incomplete corpus produces models that overfit to whatever symbols happened to finish first.

### Mode 2 — Daily Operational Refresh

**What it is**: Incremental, scheduled ingestion of the most recent data. Fast. Automated. Covers only the "active" symbol set.

**When you're in it**: Always, once the historical baseline is declared complete for a given data type. The Prefect scheduler owns this mode.

**What "done" means**: The most recent N trading days have bars for all active symbols. The Prefect UI shows green for the last scheduled run.

**Flows**:
- `yfinance-daily-refresh` — runs daily after market close; incremental (queries last stored date per symbol, fetches only new bars with a 5-day overlap window)
- `massive-options-ingest` — manually triggered for new quarters as they open; not suitable for daily because the Massive free plan rate limit makes a full symbol scan too slow

**Key difference from historical mode**: Daily refresh is driven by a scheduler and covers a narrow recent window. Historical acquisition is manually initiated, covers a wide defined window, and is complete when the gap detection assertion passes — not when the clock says so.

---

## Why Unusual Options Volume Matters

Options markets are where institutional traders express directional conviction when they want size, speed, or leverage that equity markets can't provide efficiently. When a large institution believes a stock is about to move — because of earnings, M&A, a regulatory event, or accumulated research — they often position in options before the move becomes visible in the underlying.

The key insight from the spec this module is built on:

> **Unusual volume alone is not predictive. The real edge comes from aggressor-side positioning, sweep behavior, IV repricing, dealer hedging pressure, opening flow, and volatility regime alignment.**

This is the central design principle. Raw contract volume tells you something happened. It doesn't tell you *what* or *why*. The features engineered in this module are designed to answer the "what" and "why" from the structure of the trade itself.

On the Massive path, where tick-level data is unavailable, the model narrows to volume-based signals: RVOL, premium flow, and DTE filtering. These are weaker signals individually but still contain useful information when combined.

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

*Databento path only.* The Massive API provides OHLCV bars without bid/ask at trade time; `aggressor_ratio` is zero-filled on the Massive path.

### 2. Sweep Detection

A **sweep** is when a large order is broken across multiple exchanges and filled simultaneously, prioritizing speed over price. It looks like several trades hitting the ask on CBOE, AMEX, PHLX, and ISE within milliseconds — all the same contract, all the same side.

Sweeps are significant because they indicate the trader didn't want to tip their hand by posting a large visible order. They wanted to own the position *now*, before the market could react. This is almost always institutional behavior.

Detection logic in `services/ingest.py`:

```python
# Group by (symbol, strike, expiration, put_call, aggressor_side)
# Within a 500ms window, if trades hit ≥3 distinct exchanges on the same side → is_sweep = True
```

*Databento path only.* `sweep_intensity` is zero-filled on the Massive path.

### 3. Relative Volume (RVOL)

RVOL compares today's contract volume to its 20-day rolling average:

```
RVOL = current_volume / avg_volume_20d
```

An RVOL of 10x means ten times the normal number of contracts changed hands. On its own this is noise — it could be a hedger rolling, a covered call writer, or an algorithmic strategy. Combined with aggressor side and sweep detection, elevated RVOL narrows the explanation set considerably.

**Databento path**: RVOL is computed from trade `size` (contract count) per 5-minute bucket.  
**Massive path**: RVOL is computed from bar `volume` (the aggregate count per bar).

### 4. Volume / Open Interest

```
Vol/OI = today's volume / existing open interest
```

When this ratio exceeds 1.0, more contracts traded today than currently exist as open positions. This strongly suggests **new position opening** rather than closing or rolling. Opening flow is more predictive than closing flow because it represents new directional conviction, not someone exiting a prior bet.

*Databento path only.* OI is not available in Massive OHLCV bars; `vol_oi_ratio` is zero-filled on the Massive path.

### 5. Premium Flow

```
Premium = price × 100 × contracts
```

Raw dollar value of the bet. A trader buying 100 contracts of a $2.00 premium call is spending $20,000. A sweep of 5,000 contracts at $1.50 is $750,000. Premium flow captures the economic commitment behind the activity.

**Databento path**: `premium = price × 100 × size` per individual trade, then summed per bucket.  
**Massive path**: `premium_flow = close × volume × 100` using the bar close price as a price proxy.

### 6. Delta Exposure

```
Delta Exposure = delta × contracts × 100
```

Delta is the options Greek measuring sensitivity to underlying price movement. Delta Exposure translates contract volume into equivalent share exposure. High aggregate delta exposure on one side indicates significant directional positioning.

*Databento path only.* Greeks require bid/ask and underlying price at trade time; `delta_exposure` is zero-filled on the Massive path.

### 7. IV Rank

```
IV Rank = (current_iv - iv_52w_low) / (iv_52w_high - iv_52w_low)
```

IV Rank measures where implied volatility sits relative to its past year's range. An IV Rank of 0.90 means IV is at the 90th percentile of its 52-week range — expensive options. When someone buys expensive options aggressively (high aggressor ratio, high RVOL, sweep behavior), it's a stronger signal than the same activity when IV is cheap.

*Databento path only.* IV computation requires bid/ask/underlying at trade time; `iv_rank` is zero-filled on the Massive path.

---

## Feature Availability by Data Source

| Feature | Databento | Massive | Notes |
|---|---|---|---|
| `rvol` | ✅ real | ✅ real | Different computation basis (see above) |
| `premium_flow` | ✅ real | ✅ real | Massive uses close as price proxy |
| `days_to_exp` | ✅ real | ✅ real | From contract expiration date |
| `sweep_intensity` | ✅ real | ⬜ 0.0 | Requires tick-level multi-exchange trades |
| `aggressor_ratio` | ✅ real | ⬜ 0.0 | Requires bid/ask at trade time |
| `delta_exposure` | ✅ real | ⬜ 0.0 | Requires Greeks (Black-Scholes) |
| `iv_rank` | ✅ real | ⬜ 0.0 | Requires IV history |
| `vol_oi_ratio` | ✅ real | ⬜ 0.0 | Requires open interest |

Zero-filled fields are structurally present in `options_features` — the schema does not change by data source. This means a model trained on Databento features will receive correct feature vectors at inference time regardless of which path produced the features, but the signal interpretation changes.

---

## Data Flow

### Databento Path

```
OPRA .dbn.zst file (Databento)
        │
        ▼
services/ingest.py
  - parse raw trade records
  - enrich with Greeks (services/greeks.py → py_vollib)
  - infer aggressor side per trade (bid/ask comparison)
  - detect sweeps within 500ms multi-exchange windows
  - bulk insert → options_trades (QuestDB)
        │
        ▼
services/features.py  [data_source="databento"]
  - read from: options_trades
  - aggregate into 5-minute buckets per (symbol, strike, expiration, put_call)
  - compute: RVOL, Vol/OI, premium_flow, sweep_intensity,
             aggressor_ratio, delta_exposure, IV rank, days_to_exp
  - write → options_features (QuestDB)
        │
        ▼
services/labels.py  [data_source="databento"]
  - read equity prices from: trades_data (Databento equity tick table)
  - label_24h = 1 if abs(future - now) / now > 0.02
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

### Massive Path

```
Massive API  (REST, rate-limited ~5 req/min)
        │
        ▼
services/massive_ingest.py  [CLI: cli/ingest_massive.py]
  - GET /v3/reference/options/contracts → options_contracts (metadata)
  - GET /v2/aggs/ticker/{contract}/...  → options_bars (OHLCV per contract)
  - GET /v2/aggs/ticker/{symbol}/...    → underlying_bars (equity OHLCV)
  - write run metadata                 → options_ingest_runs
  - orchestrated by Prefect flow:      → app/flows/massive_ingest_flow.py
        │
        ▼
services/features.py  [data_source="massive"]
  - read from: options_bars
  - aggregate into 5-minute (or bar-resolution) buckets
  - compute: RVOL (volume-based), premium_flow (close×volume×100), days_to_exp
  - zero-fill: sweep_intensity=0, aggressor_ratio=0,
               delta_exposure=0, iv_rank=0, vol_oi_ratio=0
  - write → options_features (QuestDB)
        │
        ▼
services/labels.py  [data_source="massive"]
  - read equity prices from: underlying_bars (Massive equity OHLCV)
  - label_24h = 1 if abs(future - now) / now > 0.02
  - write label_24h back to options_features
        │
        ▼
[Same ML training and inference pipeline as Databento path]
```

### yfinance Equity Data

`yf_ohlcv_daily` is a third equity price source — daily bars fetched via yfinance for any symbol. It is used as:
- Context/regime features (SPY, QQQ daily returns)
- A fallback equity price source when neither `trades_data` nor `underlying_bars` covers a symbol

The Prefect `yfinance-daily-refresh` flow keeps this table current automatically.

---

## Database Schema

### Databento Tables

#### `options_trades`

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

### Massive API Tables

> These tables are pending rename to `msv_` prefix (e.g., `options_bars` → `msv_options_bars`). The rename requires CREATE→INSERT→DROP because QuestDB has no ALTER TABLE RENAME. Until renamed, code references the current names.

#### `options_bars` (→ `msv_options_bars`)

OHLCV aggregate bars per options contract from the Massive API.

| Column | Type | Description |
|---|---|---|
| `ts_event` | TIMESTAMP | Bar open timestamp (designated) |
| `massive_ticker` | SYMBOL | Massive ticker (e.g., `O:TSLA250117C00200000`) |
| `underlying_symbol` | SYMBOL | Underlying equity ticker |
| `expiration_date` | DATE | Contract expiration |
| `strike_price` | DOUBLE | Strike price |
| `contract_type` | SYMBOL | `call` or `put` |
| `bar_multiplier` | INT | Bar size multiplier |
| `bar_timespan` | SYMBOL | Bar timespan (`minute`, `day`, etc.) |
| `open` | DOUBLE | Bar open price |
| `high` | DOUBLE | Bar high price |
| `low` | DOUBLE | Bar low price |
| `close` | DOUBLE | Bar close price |
| `volume` | LONG | Contracts traded in bar |
| `transactions` | LONG | Number of transactions (nullable) |
| `vwap` | DOUBLE | Volume-weighted average price (nullable) |
| `source` | SYMBOL | Always `massive` |
| `ingest_run_id` | STRING | Links to `options_ingest_runs` |

#### `underlying_bars` (→ `msv_underlying_bars`)

OHLCV aggregate bars for the underlying equity, fetched alongside option contract bars. Window is extended 30 days past the option ingest end date to support label generation.

| Column | Type | Description |
|---|---|---|
| `ts_event` | TIMESTAMP | Bar open timestamp (designated) |
| `symbol` | SYMBOL | Equity ticker |
| `bar_multiplier` | INT | Bar size multiplier |
| `bar_timespan` | SYMBOL | Bar timespan |
| `open` | DOUBLE | Bar open price |
| `high` | DOUBLE | Bar high price |
| `low` | DOUBLE | Bar low price |
| `close` | DOUBLE | Bar close price |
| `volume` | LONG | Shares traded in bar |
| `transactions` | LONG | Number of transactions (nullable) |
| `vwap` | DOUBLE | Volume-weighted average price (nullable) |
| `source` | SYMBOL | Always `massive` |
| `ingest_run_id` | STRING | Links to `options_ingest_runs` |

#### `options_contracts` (→ `msv_options_contracts`)

Contract reference metadata fetched from the Massive `/v3/reference/options/contracts` endpoint.

| Column | Type | Description |
|---|---|---|
| `fetched_at` | TIMESTAMP | When metadata was fetched (designated) |
| `massive_ticker` | STRING | Massive contract ticker |
| `underlying_symbol` | STRING | Underlying ticker |
| `contract_type` | STRING | `call` or `put` |
| `expiration_date` | STRING | Expiration date (YYYY-MM-DD) |
| `strike_price` | DOUBLE | Strike price |
| `shares_per_contract` | DOUBLE | Multiplier (typically 100) |
| `exercise_style` | STRING | `american` or `european` |
| `primary_exchange` | STRING | Primary listing exchange |
| `active` | BOOLEAN | Whether contract is still active |
| `as_of` | STRING | As-of date used in the API request |
| `source` | STRING | Always `massive` |

#### `options_ingest_runs` (→ `msv_ingest_runs`)

Tracks each Massive ingest job for observability and idempotency.

| Column | Type | Description |
|---|---|---|
| `ts_started` | TIMESTAMP | Job start time (designated) |
| `ingest_run_id` | STRING | UUID for this run |
| `source` | STRING | Always `massive` |
| `underlying_symbol` | STRING | Symbol ingested |
| `start_date` | STRING | Requested start date |
| `end_date` | STRING | Requested end date |
| `requested_resolution` | STRING | Bar resolution (e.g., `1/minute`) |
| `contracts_discovered` | LONG | Contracts returned by reference API |
| `contracts_ingested` | LONG | Contracts with at least one bar written |
| `bars_written` | LONG | Total option bars written |
| `underlying_bars_written` | LONG | Underlying equity bars written |
| `status` | STRING | `running`, `completed`, or `error` |
| `error` | STRING | Error message if failed (nullable) |
| `ts_finished` | TIMESTAMP | Job end time (nullable) |

### Shared / Derived Tables

#### `options_features`

One row per (symbol, strike, expiration, put_call, 5-minute bucket). This is the ML input table for the 24h Unusual Volume Detector. Populated by `services/features.py` on either data source path.

| Column | Type | Description |
|---|---|---|
| `ts_event` | TIMESTAMP | Bucket timestamp |
| `symbol` | SYMBOL | Underlying ticker |
| `strike` | DOUBLE | Strike price |
| `expiration` | DATE | Expiration date |
| `put_call` | SYMBOL | CALL or PUT |
| `rvol` | DOUBLE | Relative volume vs 20-day average |
| `vol_oi_ratio` | DOUBLE | Volume / open interest (0.0 on Massive path) |
| `premium_flow` | DOUBLE | Dollar premium in bucket |
| `sweep_intensity` | DOUBLE | Sweep fraction in bucket (0.0 on Massive path) |
| `aggressor_ratio` | DOUBLE | Buy premium / total premium (0.0 on Massive path) |
| `delta_exposure` | DOUBLE | Net delta × contracts × 100 (0.0 on Massive path) |
| `iv_rank` | DOUBLE | IV percentile in 52-week range (0.0 on Massive path) |
| `days_to_exp` | INT | Days until expiration |
| `label_24h` | INT | 1 = underlying moved >2% in 24h, 0 = no, NULL = unlabeled |

#### `yf_ohlcv_daily`

Daily equity OHLCV bars fetched via yfinance. Covers SPY, QQQ, TSLA, NVDA, AAPL, AMD, META. Kept current by the Prefect `yfinance-daily-refresh` flow.

| Column | Type | Description |
|---|---|---|
| `ts_event` | TIMESTAMP | Bar date at midnight UTC (designated) |
| `symbol` | STRING | Equity ticker |
| `instrument_id` | LONG | MarketAI instrument ID |
| `open` | DOUBLE | Day open |
| `high` | DOUBLE | Day high |
| `low` | DOUBLE | Day low |
| `close` | DOUBLE | Day close |
| `volume` | LONG | Shares traded |
| `source` | STRING | Always `yfinance` |

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

**Data leakage prevention**: `labels.py` reads only equity prices from `trades_data` or `underlying_bars` for the future price, never future IV, OI, or options pricing. The labeling function is deliberately separated from feature engineering to make this boundary explicit.

**Normalizer discipline**: `SequenceNormalizer` is fit on the training split only, then applied to validation and inference. Mean and std from the future cannot influence training data normalization.

**Walk-forward splits**: `evaluation/metrics.py:walk_forward_splits()` uses expanding windows — each fold's test set is strictly after its training set. This prevents any form of look-ahead.

**Survivorship bias mitigation**: The ingestion pipeline processes whatever data you provide, including delisted symbols and expired options. The model trains on the data you feed it.

**Source consistency**: Train and serve with the same `data_source`. A model trained on Databento features has a zero-free feature distribution; serving it against Massive features (five fields zero-filled) will degrade signal quality due to distribution mismatch.

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

| Feature | Description | Databento | Massive |
|---|---|---|---|
| `cluster_premium_total` | Total premium committed that day for this (symbol, strike, expiration, put_call) | ✅ | ✅ (close×volume×100) |
| `cluster_size_max` | Largest single order in the cluster | ✅ | ✅ (bar volume) |
| `cluster_trade_count` | Distinct buy trades in the daily window | ✅ | ✅ (transactions proxy) |
| `strike_concentration` | `1 - std(strikes) / mean(strikes)` per (symbol, day); 1.0 = all flow on one strike | ✅ | ✅ |
| `avg_dte` | Average days to expiration across cluster trades | ✅ | ✅ |
| `otm_pct` | Average out-of-the-money percentage (from underlying_bars merge_asof on Massive path) | ✅ | ✅ |
| `avg_delta` | Average delta of cluster; 0.3–0.5 = directional bet, not hedge | ✅ | ⬜ 0.0 |
| `premium_per_trade` | `cluster_premium_total / cluster_trade_count`; large = conviction per order | ✅ | ✅ |
| `vol_oi_ratio` | Cluster size / open interest; >1 = new position opening | ✅ | ⬜ 0.0 |
| `iv_rank` | IV percentile vs available history; buying into high-IV = strong conviction | ✅ | ⬜ 0.0 |
| `accumulation_days` | Distinct qualifying buy days in past 5 calendar days per contract | ✅ | ✅ |
| `call_put_ratio` | Call premium / total premium per (symbol, day) | ✅ | ✅ |

### Whale Data Flow

#### Databento Path

```
options_trades (enriched tick data)
        │
        ▼  Filter: aggressor=BUY, DTE 14-60, premium >= $25k
        │
services/whale_features.py  [data_source="databento"]
  - copy filtered trades → whale_trades
  - aggregate by (symbol, strike, expiration, put_call, day)
  - compute cluster features (premium, concentration, accumulation)
  - real avg_delta, iv_rank, vol_oi_ratio from Greeks + OI
  - write → whale_features (QuestDB)
        │
        ▼
services/whale_labels.py  [data_source="databento"]
  - look up equity price from trades_data at ts_event and +28 days
  - label_4w = 1 if abs(future - now) / now > 0.05
  - batch queries + merge_asof (no N+1, no leakage)
```

#### Massive Path

```
options_bars (OHLCV aggregate bars)
        │
        ▼  Filter: close*volume*100 >= $25k, DTE 14-60
        │
services/whale_features.py  [data_source="massive"]
  - filter bars by premium proxy and DTE
  - aggregate by (symbol, strike, expiration, put_call, day)
  - enrich otm_pct via merge_asof against underlying_bars
  - zero-fill: avg_delta=0, iv_rank=0, vol_oi_ratio=0
  - transactions column used as cluster_trade_count proxy
  - write → whale_features (QuestDB)
        │
        ▼
services/whale_labels.py  [data_source="massive"]
  - look up equity price from underlying_bars at ts_event and +28 days
  - label_4w = 1 if abs(future - now) / now > 0.05
```

```
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

**`whale_trades`** — filtered raw trades qualifying as potential whale activity (Databento path only):

| Column | Type | Description |
|---|---|---|
| `ts_event` | TIMESTAMP | Trade timestamp |
| `symbol` | SYMBOL | Underlying ticker |
| `strike`, `expiration`, `put_call` | — | Contract identity |
| `price`, `size`, `premium` | DOUBLE/LONG | Execution details |
| `delta`, `iv`, `open_interest` | DOUBLE | Greeks and OI at execution |
| `days_to_exp` | INT | DTE at trade time (14-60) |
| `otm_pct` | DOUBLE | (strike - underlying) / underlying |

**`whale_features`** — daily cluster signals per contract (both paths):

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
POST /api/v1/options/whale/features/compute?symbol=TSLA&start_date=...&end_date=...&data_source=massive
POST /api/v1/options/whale/labels/generate?symbol=TSLA&start_date=...&end_date=...&data_source=massive
POST /api/v1/options/whale/predict
  Body: WhaleSnapshot (symbol, strike, expiration, put_call, cluster_premium_total, ...)
  Returns: { whale_signal_score, model_loaded, scored_at, ...snapshot fields }

GET /api/v1/options/whale/signals?n=20&lookback_days=5
  Returns: { signals: [...ranked by whale_signal_score desc], count }
```

Note: `lookback_days` not `lookback_minutes` — whale signals are day-granularity.

---

## Module Structure

```
modules/options/
├── router.py                   # Mounts all sub-routers at /api/v1/options
├── db/
│   └── schema.py               # DDL for all tables (options_trades, options_features,
│                               #   whale_trades, whale_features)
├── api/
│   ├── ingest.py               # POST /ingest/upload (Databento .dbn.zst)
│   │                           #   GET /ingest/jobs
│   ├── features.py             # POST /features/compute?data_source=...
│   ├── labels.py               # POST /labels/generate?data_source=...
│   ├── predictions.py          # POST /predict, GET /signals
│   └── whale.py                # POST /whale/features/compute?data_source=...
│                               #   POST /whale/labels/generate?data_source=...
│                               #   POST /whale/predict, GET /whale/signals
├── services/
│   ├── greeks.py               # Black-Scholes via py_vollib (Databento path)
│   ├── ingest.py               # Parse, enrich, sweep-detect, bulk insert (Databento)
│   ├── massive_ingest.py       # Massive API client, rate-limited fetch, QuestDB write
│   ├── features.py             # 5-min feature aggregation; data_source param
│   ├── labels.py               # 24h future return labeling; data_source param
│   ├── inference.py            # 24h model loader + signal ranking
│   ├── whale_features.py       # Daily whale cluster aggregation; data_source param
│   ├── whale_labels.py         # 28-day / 5% move labeling; data_source param
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

The `data_source` parameter is passed through the API endpoint into the service layer. All four affected services (`features.py`, `labels.py`, `whale_features.py`, `whale_labels.py`) read from different tables and apply different enrichment logic depending on the value (`"databento"` or `"massive"`).

---

## API Endpoints

All endpoints are mounted at `/api/v1/options/` in the Python service. In production, access through the NestJS gateway (`/api/v1/`) which enforces JWT authentication.

### Ingestion

```
# Databento path — upload a .dbn.zst OPRA file
POST /api/v1/options/ingest/upload
  Body: multipart file (.dbn.zst)
  Returns: { job_id, status, message }

GET /api/v1/options/ingest/jobs
  Returns: list of all ingestion jobs

GET /api/v1/options/ingest/jobs/{job_id}
  Returns: { id, filename, status, records_processed, error, ... }

# Massive path — trigger via CLI or Prefect flow (no HTTP endpoint for Massive ingest)
# See: cli/ingest_massive.py and app/flows/massive_ingest_flow.py
```

### Feature Engineering

```
POST /api/v1/options/features/compute
  ?symbol=TSLA&start_date=2026-01-01&end_date=2026-03-31&data_source=massive
  Returns: { status, rows_written, symbol }
```

Triggers aggregation into `options_features`. `data_source` controls which source table is read. Must be run before training.

### Label Generation

```
POST /api/v1/options/labels/generate
  ?symbol=TSLA&start_date=2026-01-01&end_date=2026-03-31&data_source=massive
  Returns: { status, labels_written, symbol }
```

Joins `options_features` timestamps against equity prices to populate `label_24h`. `data_source` controls whether equity prices are read from `trades_data` (Databento) or `underlying_bars` (Massive). Must be run before training.

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

### Databento Path (full features)

```bash
# 1. Ingest OPRA data
curl -X POST http://localhost:8000/api/v1/options/ingest/upload \
  -F "file=@/path/to/opra_data.dbn.zst"

# 2. Compute features (Databento path — all features real)
curl -X POST "http://localhost:8000/api/v1/options/features/compute?symbol=SPY&start_date=2026-01-01&end_date=2026-05-17&data_source=databento"

# 3. Generate labels (reads equity prices from trades_data)
curl -X POST "http://localhost:8000/api/v1/options/labels/generate?symbol=SPY&start_date=2026-01-01&end_date=2026-05-17&data_source=databento"

# 4. Train LightGBM baseline (Phase 1)
docker exec market_python_service python -m app.modules.options.ml.training.train_lgbm --symbol SPY

# 5. (Optional) Train LSTM sequence model (Phase 2)
docker exec market_python_service python -m app.modules.options.ml.training.train_sequence --symbol SPY --window 20
```

### Massive Path (RVOL + premium flow only)

```bash
# 1. Ingest via CLI (Massive API — use Prefect flow for scheduled runs)
python -m app.cli.ingest_massive \
  --symbol TSLA --start 2025-01-01 --end 2025-03-31 \
  --contract-type call --bar-timespan minute --bar-multiplier 1

# 2. Compute features (Massive path — sweep/aggressor/delta/iv zero-filled)
curl -X POST "http://localhost:8000/api/v1/options/features/compute?symbol=TSLA&start_date=2025-01-01&end_date=2025-03-31&data_source=massive"

# 3. Generate labels (reads equity prices from underlying_bars)
curl -X POST "http://localhost:8000/api/v1/options/labels/generate?symbol=TSLA&start_date=2025-01-01&end_date=2025-03-31&data_source=massive"

# 4. Train LightGBM (same command — model learns from available features)
docker exec market_python_service python -m app.modules.options.ml.training.train_lgbm --symbol TSLA
```

### Whale Pipeline

```bash
# 1. Compute whale features
curl -X POST "http://localhost:8000/api/v1/options/whale/features/compute?symbol=TSLA&start_date=2025-01-01&end_date=2025-03-31&data_source=massive"

# 2. Generate 4-week labels (needs 28 days of future equity data in underlying_bars)
curl -X POST "http://localhost:8000/api/v1/options/whale/labels/generate?symbol=TSLA&start_date=2025-01-01&end_date=2025-03-01&data_source=massive"

# 3. Train LightGBM
docker exec market_python_service python -m app.modules.options.ml.training.train_whale_lgbm --symbol TSLA

# 4. Test whale signals
curl "http://localhost:8000/api/v1/options/whale/signals?n=10&lookback_days=5"
```

### Shared

```bash
# View MLflow runs
open http://localhost:5000

# Prefect orchestration UI
open http://localhost:4200
```

---

## Extending to New Data Sources

The `data_source` parameter is the integration point for adding additional sources (e.g., CBOE LiveVol, Quandl, Interactive Brokers). To add a new source:

1. **Write an ingest service** — fetch data from the new source and write to a new source-prefixed table (e.g., `cboe_options_bars`). Follow the pattern in `services/massive_ingest.py`: paginated fetch, idempotent insert, run tracking.

2. **Add a `data_source` branch** in each of the four services:
   - `services/features.py` — add an `elif data_source == "newname":` block that reads from the new table and populates `options_features`
   - `services/labels.py` — add a branch that reads equity prices from whatever the new source provides
   - `services/whale_features.py` — add a branch for whale feature computation
   - `services/whale_labels.py` — add a branch for whale label generation

3. **Document feature availability** — for each feature in `options_features`, decide whether the new source provides it or whether it should be zero-filled. Zero-filling is correct when the data simply isn't available; imputing it would introduce false signal.

4. **Update the instruments table** — add source-specific instrument IDs so the instrument registry can route requests correctly.

5. **Train with the new source** — use `data_source=newname` on the `/features/compute` and `/labels/generate` calls. Train a model artifact named distinctly (e.g., `options_model_cboe.pkl`) so Databento and Massive models aren't overwritten.

The goal is that the ML training and inference code is data-source agnostic — it reads from `options_features`, which always has the same schema regardless of how it was populated. The source-specific logic lives entirely in the service layer.

---

## Known Limitations and Future Work

**Source consistency at inference**: When a Databento-trained model is served, features must come from a Databento ingest run. Serving Massive-generated features (zero-filled sweep_intensity, aggressor_ratio) against a Databento model will produce misleading signal scores. A future improvement is to tag each `options_features` row with its `data_source` and validate it at inference time.

**Greeks enrichment quality**: The current implementation computes Greeks using the trade price as the underlying price approximation. In production this should use a live underlying price feed at the moment of each trade.

**Open interest**: OPRA trade data does not include real-time OI. The `open_interest` field is populated from instrument definition records in the Databento feed when available. A separate daily OI snapshot ingestion should be added for more reliable Vol/OI ratios.

**Kafka/streaming**: The current architecture is batch-based. A streaming architecture (Redpanda/Kafka) would allow real-time feature computation as trades arrive, necessary for sub-500ms latency in a live environment.

**Cross-asset regime**: The spec calls for market regime conditioning (VIX, SPY, QQQ, interest rates). These are not yet included as features. A high-VIX regime changes what "unusual" means — RVOL of 3x is more significant in a low-volatility regime than in a panic. `yf_ohlcv_daily` contains SPY and QQQ daily bars that could serve this purpose.

**Dealer gamma exposure**: Aggregate dealer gamma positioning (GEX) is one of the most powerful contextual signals for predicting pinning behavior and volatility events, but requires modeling the market maker hedging book across the entire options chain.

**Table rename**: The Massive tables (`options_bars`, `underlying_bars`, `options_contracts`, `options_ingest_runs`) need renaming to the `msv_` prefix convention. Blocked until all active ingests complete (QuestDB requires CREATE→INSERT→DROP migration, which cannot run against a table being actively written).
