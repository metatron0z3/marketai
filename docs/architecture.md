# Architecture

## System Overview

```
                    ┌─────────────────┐
                    │   Angular FE    │
                    │  (Port 4200)    │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
              ▼              ▼              ▼
┌─────────────────┐ ┌───────────────┐ ┌─────────────────┐
│  NestJS Backend │ │ Go Streaming  │ │ Python Service  │
│  (Port 3000)    │ │ (Port 8082)   │ │ (Port 8000)     │
│                 │ │               │ │                 │
│ - Market Data   │ │ - WebSocket   │ │ - Data Ingest   │
│ - Instruments   │ │ - Live Charts │ │ - Indicators    │
│ - Indicators    │ │               │ │ - ML Pipeline   │
│ - Orchestration │ │               │ │                 │
└────────┬────────┘ └───────────────┘ └────────┬────────┘
         │                                      │
         └──────────────┬───────────────────────┘
                        ▼
              ┌─────────────────┐
              │    QuestDB      │
              │ (9000/8812)     │
              └─────────────────┘
```

## Services

### NestJS Backend (Port 3000)

**Responsibility**: API gateway, orchestration, market data queries, technical indicators

**Structure**:
```
backend-nest/src/
├── main.ts                 # Entry point
├── app.module.ts           # Root module
├── app.controller.ts       # Health, db-status
├── config/
│   └── configuration.ts    # Environment config
├── database/
│   ├── database.module.ts
│   └── questdb.service.ts  # Connection pool
└── modules/
    ├── instruments/        # Symbol lookup
    ├── market-data/        # OHLCV queries
    ├── indicators/         # Proxy to Python indicators
    └── ingest/             # Proxy to Python ingestion
```

**Why NestJS?**
- Type-safe REST API with TypeScript
- Modular architecture scales well
- Handles coordination between services
- Swagger/OpenAPI documentation built-in

### Python Service (Port 8000)

**Responsibility**: Data ingestion, indicator calculation, ML feature engineering

**Structure**:
```
python-service/app/
├── main.py                 # FastAPI entry
├── api/v1/
│   └── endpoints/
│       ├── ingest.py       # File upload & processing
│       ├── indicators.py   # RSI, VWAP, MA, Bollinger, Volume
│       └── models/         # (deprecated, use NestJS)
├── core/
│   └── db.py               # QuestDB connection
└── services/
    ├── indicators.py       # Pandas-based calculations
    └── ohlcv.py            # OHLCV aggregation
```

**Why Python?**
- Pandas/polars for data manipulation
- Technical indicator libraries (pandas-ta)
- PyTorch for ML models
- Databento SDK for market data

### Go Streaming (Port 8082)

**Responsibility**: Real-time WebSocket updates for live charts

**Why Go?**
- High-concurrency WebSocket handling
- Low latency for tick-level data
- Efficient memory usage for streaming

### QuestDB (Ports 9000, 8812)

**Responsibility**: Time-series data storage and aggregation

- **Port 9000**: HTTP API (web console, monitoring)
- **Port 8812**: PostgreSQL wire protocol (for Python/NestJS connections)

**Why QuestDB?**
- Purpose-built for time-series data
- Ultra-fast OHLCV aggregations with `SAMPLE BY`
- Per-day partitioning for scalability
- Lower resource footprint than traditional databases

### Angular Frontend (Port 4200)

**Responsibility**: Web UI, charting, indicator toggles, S/R line management

**Why Angular?**
- Enterprise-grade framework
- Strong typing (TypeScript)
- RxJS for reactive updates
- lightweight-charts integration for financial charting

## Design Rationale

1. **NestJS as gateway**: Single entry point for all client requests; decouples frontend from backend specifics
2. **Python specialists**: Data science tasks (ML, indicators) stay in Python where the ecosystem is strong
3. **Go for streaming**: Designed for high-concurrency, low-latency updates
4. **QuestDB for OHLCV**: Specialized time-series store beats general-purpose databases for this workload
5. **Skill-based task routing**: Each service has a SKILL.md that documents patterns and conventions
