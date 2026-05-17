# Unusual Volume Options ML Pipeline — Execution Plan

## Context

Extends the existing MarketAI platform (NestJS + Python FastAPI + QuestDB + Angular) with an institutional-grade ML pipeline for detecting unusual options volume and predicting underlying price expansion. All options-specific code lives in a self-contained module: `python-service/app/modules/options/`.

---

## Module Structure

```
python-service/app/modules/options/
├── __init__.py
├── router.py                        # aggregates all sub-routers; mounted at /api/v1/options
├── db/
│   ├── __init__.py
│   └── schema.py                    # create_options_tables() — called once at startup
├── api/
│   ├── __init__.py
│   ├── ingest.py                    # POST /ingest/upload, GET /ingest/jobs
│   ├── features.py                  # POST /features/compute
│   ├── labels.py                    # POST /labels/generate
│   └── predictions.py               # POST /predict, GET /signals
├── services/
│   ├── __init__.py
│   ├── greeks.py                    # Black-Scholes via py_vollib
│   ├── ingest.py                    # parse OPRA .dbn.zst, aggressor inference, sweep detection
│   ├── features.py                  # RVOL, Vol/OI, premium flow, delta exposure, IV rank
│   ├── labels.py                    # future_return_24h label generation
│   └── inference.py                 # model loader (@lru_cache) + signal scoring
└── ml/
    ├── __init__.py
    ├── features/
    │   └── feature_builder.py       # pulls labeled rows from options_features table
    ├── datasets/
    │   └── options_dataset.py       # PyTorch Dataset wrapper
    ├── models/
    │   ├── base_model.py            # BaseFinancialModel(nn.Module)
    │   └── lgbm_model.py            # LightGBM wrapper
    ├── training/
    │   ├── train_lgbm.py            # Phase 1 baseline
    │   └── train_sequence.py        # Phase 2 LSTM/Transformer
    ├── evaluation/
    │   └── metrics.py               # Sharpe, directional accuracy, walk-forward splits
    └── registry/
        └── model_registry.py        # TorchScript save/load, versioning
```

---

## Stage 1 — QuestDB Schema

`python-service/app/modules/options/db/schema.py` — `create_options_tables()`:

```sql
CREATE TABLE IF NOT EXISTS options_trades (
  ts_event TIMESTAMP,
  symbol SYMBOL,
  strike DOUBLE,
  expiration DATE,
  put_call SYMBOL,
  price DOUBLE,
  size LONG,
  bid DOUBLE,
  ask DOUBLE,
  trade_condition SYMBOL,
  exchange SYMBOL,
  iv DOUBLE,
  delta DOUBLE, gamma DOUBLE, vega DOUBLE, theta DOUBLE,
  open_interest LONG,
  aggressor_side SYMBOL,
  is_sweep BOOLEAN,
  premium DOUBLE
) TIMESTAMP(ts_event) PARTITION BY DAY;

CREATE TABLE IF NOT EXISTS options_features (
  ts_event TIMESTAMP,
  symbol SYMBOL,
  strike DOUBLE,
  expiration DATE,
  put_call SYMBOL,
  rvol DOUBLE, vol_oi_ratio DOUBLE, premium_flow DOUBLE,
  sweep_intensity DOUBLE, aggressor_ratio DOUBLE,
  delta_exposure DOUBLE, iv_rank DOUBLE, days_to_exp INT,
  label_24h INT
) TIMESTAMP(ts_event) PARTITION BY DAY;
```

**Modified files:**
- `python-service/app/core/db.py` — call `create_options_tables()` on startup
- `python-service/app/main.py` — startup event hook
- `python-service/app/api/v1/api.py` — mount options router

---

## Stage 2 — Ingestion

**Endpoints:** `POST /api/v1/options/ingest/upload`, `GET /api/v1/options/ingest/jobs`

- Accepts `.dbn.zst` OPRA files
- Background thread: parse → Greeks enrichment → aggressor inference → sweep detection → bulk insert `options_trades`
- Reuses job-tracking dict pattern from existing `ingest.py`

**Aggressor inference:**
```python
def infer_aggressor(price, bid, ask):
    if price >= ask: return "BUY"
    if price <= bid: return "SELL"
    return "MID"
```

**Sweep detection:** group by (symbol, strike, expiration, put_call) within 500ms; ≥3 exchanges same side → `is_sweep = True`

**Greeks:** `py_vollib` for IV, delta, gamma, vega, theta

---

## Stage 3 — Feature Engineering

**Endpoint:** `POST /api/v1/options/features/compute`

| Feature | Formula |
|---|---|
| RVOL | current_volume / avg_volume_20d |
| Vol/OI | size / open_interest |
| Premium Flow | price × 100 × size |
| Sweep Intensity | sweep_count / total_trades (5min window) |
| Aggressor Ratio | buy_premium / (buy_premium + sell_premium) |
| Delta Exposure | delta × size × 100 |
| IV Rank | (iv - iv_52w_low) / (iv_52w_high - iv_52w_low) |
| Days to Exp | (expiration - today).days |

---

## Stage 4 — Label Generation

**Endpoint:** `POST /api/v1/options/labels/generate`

- `label_24h = 1` if `abs(future_close_24h - close_now) / close_now > 0.02`
- Uses existing `trades_data` equity table for future prices
- **Never uses future IV, OI, or options prices**

---

## Stage 5 — ML Training

**Phase 1 — LightGBM baseline (`ml/training/train_lgbm.py`):**
- Walk-forward cross-validation; logs to MLflow
- Features: RVOL, vol_oi_ratio, premium_flow, sweep_intensity, aggressor_ratio, delta_exposure, iv_rank, days_to_exp
- Target: `label_24h`

**Phase 2 — LSTM sequence model (`ml/training/train_sequence.py`):**
- 20-period temporal windows
- All models inherit `BaseFinancialModel(nn.Module)`
- Gradient clipping `max_norm=1.0`; `AdamW` + `CosineAnnealingLR`
- Export via TorchScript

**New deps:** `lightgbm`, `torch`, `mlflow`, `py_vollib`, `scikit-learn`

---

## Stage 6 — Inference

**Endpoints:** `POST /api/v1/options/predict`, `GET /api/v1/options/signals`

- Contract snapshot → feature pipeline → model forward pass → signal score
- Latency target: <500ms
- `@lru_cache` on model/normalizer loaders

---

## Stage 7 — NestJS Gateway

New NestJS modules (each following `skills/nestjs-backend/SKILL.md`):

| Module | Endpoint | Responsibility |
|---|---|---|
| `options-signals` | `GET /api/v1/signals` | proxies Python `/options/signals`; Redis 30s cache |
| `options-flow` | `GET /api/v1/flow` | proxies Python `/options/features` |
| `predictions` | `GET/POST /api/v1/predictions` | proxies Python `/options/predict` |
| `auth` | JWT guard | protects all options endpoints |

**New deps:** `@nestjs/jwt`, `@nestjs/passport`, `passport-jwt`, `ioredis`, `@nestjs/cache-manager`

---

## Stage 8 — Docker Compose

Add to `docker-compose.yml`:
- `redis` (redis:7-alpine, port 6379)
- `mlflow` (port 5000, `mlflow_data` volume)

Update `nestjs-backend` `depends_on` to include `redis`.

---

## Stage 9 — Environment Variables

```env
MLFLOW_TRACKING_URI=http://mlflow:5000
REDIS_URL=redis://redis:6379
JWT_SECRET=<secret>
RISK_FREE_RATE=0.05
MODEL_ARTIFACTS_PATH=/app/artifacts
```

---

## Verification

1. Upload `.dbn.zst` OPRA file → `options_trades` populated in QuestDB (http://localhost:9000)
2. `POST /api/v1/options/features/compute` → `options_features` rows with non-null RVOL
3. `POST /api/v1/options/labels/generate` → `label_24h` populated
4. Run `train_lgbm.py` → MLflow run logged at http://localhost:5000
5. `POST /api/v1/options/predict` → response <500ms with `signal_score`
6. `GET /api/v1/signals` with JWT → ranked signals; cache hit on second call
