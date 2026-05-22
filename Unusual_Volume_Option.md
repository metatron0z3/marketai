# Unusual Volume Options ML Pipeline

## Objective

Build an institutional-grade ML pipeline for predicting underlying price expansion and volatility events using unusual options volume data.

The system should identify:
- aggressive positioning,
- informed order flow,
- dealer hedging pressure,
- volatility repricing,
- and asymmetric positioning before major market moves.

---

# 1. Required Data Sources

## A. Options Trade Data (Core Signal Layer)

You need:
- every options trade,
- timestamps,
- bid/ask at execution,
- contract metadata,
- size,
- aggressor side inference.

### Required Fields

| Field | Purpose |
|---|---|
| ts_event | Event timestamp |
| symbol | Underlying ticker |
| strike | Strike price |
| expiration | Expiration date |
| put_call | Option type |
| price | Premium traded |
| size | Contracts traded |
| bid | Bid at execution |
| ask | Ask at execution |
| trade_condition | Sweep/block/etc |
| exchange | Venue analysis |
| iv | Implied volatility |
| delta/gamma/vega/theta | Greeks |
| open_interest | Positioning baseline |

### Recommended Databento Feeds

- OPRA.PILLAR
- OPRA.TOP
- Instrument definitions
- MBP-1/TBBO schemas

You need:
- trades,
- top-of-book quotes,
- and instrument definitions.

---

## B. Underlying Equity Data

Required:
- OHLCV,
- VWAP,
- realized volatility,
- ATR,
- liquidity,
- relative volume.

### Required Fields

| Field | Purpose |
|---|---|
| OHLCV | Baseline price structure |
| VWAP | Institutional positioning |
| Relative volume | Event detection |
| Float | Gamma squeeze potential |
| Market cap | Regime classification |
| Beta | Risk normalization |

---

## C. Volatility Data

Required:
- implied volatility surface,
- realized volatility,
- IV rank,
- IV percentile,
- skew,
- term structure.

### Important Derived Signals

- IV expansion
- Skew shifts
- Term structure inversion

---

## D. Open Interest Data

Required:
- daily OI snapshots,
- intraday OI estimates.

Used for:
- opening vs closing detection,
- crowded strike analysis,
- gamma magnet detection.

---

## E. Market Regime Data

Required:
- VIX,
- SPY,
- QQQ,
- interest rates,
- earnings calendar,
- macroeconomic events.

---

## F. Event Data

Required:
- earnings dates,
- analyst upgrades/downgrades,
- M&A events,
- FDA decisions,
- breaking news timestamps.

---

# 2. Core Unusual Volume Features

## Relative Volume

```math
RVOL = Current Volume / Average Historical Volume
```

---

## Volume vs Open Interest

```math
Volume / Open Interest
```

High values often indicate:
- opening positions,
- institutional positioning.

---

## Premium Flow

```math
Premium = Price × 100 × Contracts
```

---

## Sweep Detection

Detect:
- same strike,
- same expiration,
- rapid multi-exchange execution,
- identical aggressor side.

This often indicates informed order flow.

---

## Delta-Adjusted Exposure

```math
Delta Exposure = Delta × Contracts × 100
```

---

# 3. Recommended Predictive Targets

## Initial Recommended Target

Binary classification:

> Predict whether the underlying moves more than X% within Y hours after unusual options activity.

### Example

- Target:
  - underlying move > 2%
  - within 24 hours.

---

# 4. Recommended System Architecture

```plaintext
Databento Streams
        ↓
Python Ingestion
        ↓
Kafka / Redpanda
        ↓
Feature Engineering
        ↓
QuestDB + Parquet
        ↓
Training Pipeline
        ↓
LightGBM / XGBoost
        ↓
FastAPI Inference Service
        ↓
NestJS Gateway
        ↓
Frontend / Alerting
```

---

# 5. Technology Stack

| Layer | Technology |
|---|---|
| Data ingestion | Python |
| Streaming | Kafka / Redpanda |
| Storage | QuestDB |
| Cold storage | Parquet + S3/MinIO |
| Feature engineering | Polars |
| Orchestration | Airflow / Prefect |
| Model serving | FastAPI |
| API gateway | NestJS |
| Cache | Redis |
| ML framework | LightGBM / XGBoost |
| Deep learning | PyTorch |

---

# 6. Storage Design

## Hot Storage

### QuestDB

Use for:
- real-time analytics,
- intraday querying,
- time-series feature generation.

---

## Cold Storage

### Parquet

Recommended partitioning:

```plaintext
/options/year=2026/month=05/day=15/symbol=SPY/
```

---

# 7. Pipeline Roadmap

## Stage 1 — Ingestion Layer

### Service A — OPRA Consumer

Responsibilities:
- consume Databento streams,
- normalize trades,
- enrich metadata,
- publish Kafka events.

---

### Service B — Quote Joiner

Responsibilities:
- join trades with NBBO,
- infer aggressor side,
- classify sweeps/blocks.

---

### Service C — Greeks Calculator

Responsibilities:
- calculate delta,
- gamma,
- vega,
- theta,
- IV metrics.

Recommended libraries:
- py_vollib,
- QuantLib.

---

# 8. Feature Engineering

## Contract-Level Features

- RVOL
- Volume/OI
- Premium flow
- Sweep intensity
- Aggressor ratio

---

## Underlying Features

- Momentum
- ATR
- VWAP distance
- Realized volatility

---

## Dealer Exposure Features

- Gamma exposure
- Delta imbalance

---

## Time Features

- Time-to-expiration
- Intraday session
- Days-to-earnings

---

# 9. Label Generation

Examples:

```python
future_return_24h > 0.02
```

or:

```python
max_move_next_6h > threshold
```

Avoid:
- data leakage,
- future-looking features.

---

# 10. Model Training Roadmap

## Phase 1 — Baseline Models

Recommended:
- LightGBM,
- XGBoost.

Reason:
- excellent performance on tabular financial datasets.

---

## Phase 2 — Sequence Models

After baseline validation:

- Temporal CNNs
- LSTMs
- Transformers

---

# 11. Real-Time Signal Engine

Pipeline:

```plaintext
Trade arrives
→ Quote join
→ Feature generation
→ Model inference
→ Signal scoring
→ Alert creation
```

Latency target:
- under 500ms.

---

# 12. NestJS API Responsibilities

NestJS should act as:
- API gateway,
- authentication layer,
- orchestration layer.

---

## Recommended APIs

### REST Endpoints

- `/signals`
- `/contracts`
- `/flow`
- `/predictions`

---

## Additional Responsibilities

- JWT authentication
- WebSocket streaming
- Redis caching
- User management
- Rate limiting

---

# 13. FastAPI ML Service Responsibilities

Responsibilities:
- feature retrieval,
- inference,
- model scoring,
- ranking signals.

---

# 14. Biggest Technical Challenges

## A. Trade Classification

Correctly determining:
- bid-side,
- ask-side,
- midpoint executions.

Critical for accurate signal generation.

---

## B. Time Alignment

Trades and quotes must align within milliseconds.

---

## C. Survivorship Bias

Include:
- delisted symbols,
- expired options.

---

## D. Data Leakage

Never include:
- future IV,
- future OI,
- future prices,
inside feature generation.

---

# 15. Recommended Python Libraries

| Area | Library |
|---|---|
| DataFrames | Polars |
| ML | LightGBM |
| Deep Learning | PyTorch |
| Options Math | py_vollib |
| Backtesting | Backtrader |
| Validation | Great Expectations |
| APIs | FastAPI |
| Streaming | Faust/Kafka |

---

# 16. Long-Term Advanced Features

Future enhancements:
- dark pool integration,
- dealer gamma models,
- volatility surface embeddings,
- graph neural networks,
- reinforcement learning,
- order flow embeddings,
- cross-asset correlations.

---

# 17. Most Important Insight

Unusual volume alone is not predictive.

The real predictive edge comes from:
- aggressor-side positioning,
- sweep behavior,
- IV repricing,
- dealer hedging pressure,
- opening flow,
- liquidity structure,
- and volatility regime alignment.

That is where institutional-grade signal quality emerges.
