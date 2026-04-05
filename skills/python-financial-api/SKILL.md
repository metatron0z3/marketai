---
name: python-financial-api
description: >
  Python API expert for processing complex financial and scientific data from QuestDB and
  other sources. Use this skill for ALL Python work: FastAPI endpoints, QuestDB queries,
  pandas/numpy/polars data processing, financial calculations (indicators, risk metrics,
  time series analysis), data ingestion pipelines, scientific computing, and Python container
  configuration.
  Triggers on: Python, FastAPI, QuestDB, pandas, polars, numpy, financial data processing,
  OHLCV calculations, technical indicators, backtesting, data pipeline, time series, scientific
  data, or any work in the Python API container.
  IMPORTANT: This skill has a companion — ml-pipeline/SKILL.md handles PyTorch model training,
  feature engineering, and inference. Load BOTH skills when the task involves ML or model
  serving inside this container. This skill owns the API layer; ml-pipeline owns the model layer.
  Always load this skill before writing any Python code for this platform.
---

# Python Financial API Expert — QuestDB + Data Science

You are an expert Python API engineer specializing in financial data processing. You build fast, well-typed FastAPI services that query QuestDB efficiently and expose clean, documented endpoints.

## Stack
- **Framework**: FastAPI (latest)
- **Database**: QuestDB (via PostgreSQL wire + REST API)
- **Data**: pandas, polars (prefer polars for performance), numpy
- **Financial**: `pandas-ta` for technical indicators, `scipy` for scientific
- **Validation**: Pydantic v2
- **Async DB**: `asyncpg` (PostgreSQL wire protocol to QuestDB)
- **Testing**: pytest + httpx (async test client)
- **Container**: Docker

---

## Project Structure

```
python-api/
├── app/
│   ├── main.py                   # FastAPI app + router registration
│   ├── config.py                 # Settings via pydantic-settings
│   ├── database/
│   │   ├── questdb.py            # QuestDB connection pool
│   │   └── queries/
│   │       └── market_data.py    # Raw SQL queries (keep SQL out of routers)
│   ├── routers/
│   │   └── market_data.py        # FastAPI router
│   ├── services/
│   │   └── indicators.py         # Business logic, calculations
│   ├── models/
│   │   ├── requests.py           # Pydantic request models
│   │   └── responses.py          # Pydantic response models
│   └── utils/
│       └── timeframe.py          # Timeframe parsing, alignment helpers
├── tests/
│   └── test_market_data.py
├── Dockerfile
└── requirements.txt
```

---

## QuestDB Integration

### Connection (asyncpg to QuestDB's PostgreSQL wire)
```python
# app/database/questdb.py
import asyncpg
from app.config import settings

_pool: asyncpg.Pool | None = None

async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            host=settings.questdb_host,
            port=settings.questdb_pg_port,   # default 8812
            user=settings.questdb_user,
            password=settings.questdb_password,
            database="qdb",
            min_size=2,
            max_size=10,
        )
    return _pool

async def fetch(query: str, *args) -> list[asyncpg.Record]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch(query, *args)
```

### QuestDB Query Patterns
```python
# app/database/queries/market_data.py

# ✅ QuestDB uses SQL with time-series extensions
# Use SAMPLE BY for OHLCV aggregation — do NOT do this in pandas
OHLCV_QUERY = """
SELECT
    symbol,
    first(price)  AS open,
    max(price)    AS high,
    min(price)    AS low,
    last(price)   AS close,
    sum(volume)   AS volume,
    timestamp     AS time
FROM ticks
WHERE symbol = $1
  AND timestamp BETWEEN $2 AND $3
SAMPLE BY $4   -- e.g. '1m', '5m', '1h', '1d'
ORDER BY timestamp
"""

# ✅ Use designated timestamp column for range queries — always faster
LATEST_TICKS_QUERY = """
SELECT price, volume, timestamp
FROM ticks
WHERE symbol = $1
LATEST ON timestamp PARTITION BY symbol
"""
```

**QuestDB-Specific Rules:**
- Always use `SAMPLE BY` for time aggregation — never aggregate in Python
- Use `LATEST ON ... PARTITION BY` for latest-per-symbol queries
- Designated timestamp column (`timestamp`) is always indexed — use it in WHERE
- Avoid `SELECT *` on tick tables — these can have billions of rows

---

## FastAPI Patterns

### Config (Pydantic Settings)
```python
# app/config.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    questdb_host: str = "questdb"
    questdb_pg_port: int = 8812
    questdb_user: str = "admin"
    questdb_password: str
    api_key: str   # for auth between services

    class Config:
        env_file = ".env"

settings = Settings()
```

### Router + Service Pattern
```python
# app/routers/market_data.py
from fastapi import APIRouter, Depends, Query
from app.models.responses import OHLCVResponse
from app.services.indicators import IndicatorService

router = APIRouter(prefix="/market-data", tags=["Market Data"])

@router.get("/ohlcv/{symbol}", response_model=list[OHLCVResponse])
async def get_ohlcv(
    symbol: str,
    timeframe: str = Query(default="1h", pattern=r"^\d+[mhd]$"),
    start: datetime = Query(...),
    end: datetime = Query(...),
    service: IndicatorService = Depends(),
):
    """Returns OHLCV bars for the given symbol and timeframe."""
    return await service.get_ohlcv(symbol, timeframe, start, end)
```

### Response Models (Pydantic v2)
```python
# app/models/responses.py
from pydantic import BaseModel, ConfigDict
from datetime import datetime

class OHLCVResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    symbol: str
    time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
```

---

## Financial Calculations

### Technical Indicators (pandas-ta)
```python
import pandas as pd
import pandas_ta as ta

def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Input df must have columns: open, high, low, close, volume
    with a DatetimeIndex.
    """
    df.ta.rsi(length=14, append=True)           # RSI_14
    df.ta.macd(fast=12, slow=26, append=True)   # MACD columns
    df.ta.bbands(length=20, append=True)        # Bollinger Bands
    df.ta.atr(length=14, append=True)           # Average True Range
    return df
```

### Polars for High-Volume Processing
```python
import polars as pl

# Prefer polars over pandas for large datasets (faster, lower memory)
def process_ticks_polars(raw_records: list[dict]) -> pl.DataFrame:
    df = pl.from_records(raw_records)
    return (
        df
        .sort("timestamp")
        .with_columns([
            pl.col("price").rolling_mean(window_size=20).alias("sma_20"),
            (pl.col("price") - pl.col("price").shift(1)).alias("price_change"),
        ])
        .filter(pl.col("volume") > 0)
    )
```

---

## Testing

```python
# tests/test_market_data.py
import pytest
from httpx import AsyncClient
from app.main import app

@pytest.mark.asyncio
async def test_ohlcv_returns_data():
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get(
            "/market-data/ohlcv/AAPL",
            params={"timeframe": "1h", "start": "2024-01-01T00:00:00", "end": "2024-01-02T00:00:00"},
            headers={"X-API-Key": "test-key"},
        )
    assert response.status_code == 200
    data = response.json()
    assert len(data) > 0
    assert "open" in data[0]
```

---

## Dockerfile

```dockerfile
FROM python:3.12-slim AS builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

FROM python:3.12-slim
WORKDIR /app
COPY --from=builder /root/.local /root/.local
COPY app/ ./app/
ENV PATH=/root/.local/bin:$PATH
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

## Checklist Before Completing Any Task

- [ ] All request/response shapes defined as Pydantic models — no raw dicts
- [ ] QuestDB time aggregation done via `SAMPLE BY` in SQL — not in Python
- [ ] Config accessed via `settings` object — never `os.environ` raw
- [ ] Large data processing uses polars — not pandas
- [ ] New env vars added to `config.py` and `.env.example`
- [ ] `/health` endpoint present and returns DB connectivity status
- [ ] Async all the way — no blocking calls in route handlers
- [ ] pytest tests cover happy path and error cases
- [ ] OpenAPI docs auto-generated — verify schema is clean before handing to NestJS
