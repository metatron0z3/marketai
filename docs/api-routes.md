# API Routes

## NestJS Backend (Port 3000)

### Health & Status

| Method | Route | Description |
|--------|-------|-------------|
| GET | `/` | Welcome message |
| GET | `/health` | Health check |
| GET | `/db-status` | Database connection status |

### Instruments

| Method | Route | Description |
|--------|-------|-------------|
| GET | `/api/v1/instruments` | List all instruments |
| GET | `/api/v1/instruments/:symbol` | Get instrument by symbol (e.g., SPY) |

### Market Data

| Method | Route | Description |
|--------|-------|-------------|
| GET | `/api/v1/market-data` | Get OHLCV data |

**Query Parameters**:
- `instrument_id` (required): Symbol ID (15144=SPY, 13340=QQQ, 16244=TSLA)
- `timeframe` (required): 5m, 1h, or 1d
- `start_date` (required): ISO date (e.g., 2025-01-01)
- `end_date` (required): ISO date (e.g., 2025-01-31)

**Response**:
```json
{
  "data": [
    {
      "ts": "2025-01-01T09:30:00Z",
      "open": 500.50,
      "high": 502.00,
      "low": 499.75,
      "close": 501.25,
      "volume": 1000000
    }
  ]
}
```

### Technical Indicators

| Method | Route | Description |
|--------|-------|-------------|
| GET | `/api/v1/indicators` | Get calculated indicators |

**Query Parameters**:
- `instrument_id` (required): Symbol ID
- `timeframe` (required): 5m, 1h, or 1d
- `start_date` (required): ISO date
- `end_date` (required): ISO date
- `indicators` (optional): Comma-separated list (rsi, vwap, ma7, ma20, ma200, bollinger, volume)

**Response**:
```json
{
  "rsi": [...],
  "vwap": [...],
  "ma7": [...],
  "ma20": [...],
  "ma200": [...],
  "bollinger": {
    "upper": [...],
    "middle": [...],
    "lower": [...]
  },
  "volume": [...]
}
```

### Data Ingestion

| Method | Route | Description |
|--------|-------|-------------|
| POST | `/api/v1/ingest/upload` | Upload .dbn.zst or .zip file |
| GET | `/api/v1/ingest/jobs` | List ingest jobs |
| GET | `/api/v1/ingest/jobs/:id` | Get job status |

**Upload Response**:
```json
{
  "job_id": "uuid",
  "status": "processing",
  "file": "data.dbn.zst",
  "records": 0
}
```

---

## Python Service (Port 8000)

Direct endpoint access (NestJS proxies these to avoid duplication).

### Ingest Endpoints

- `POST /api/v1/ingest/upload` — File upload handler
- `GET /api/v1/ingest/jobs` — Job list
- `GET /api/v1/ingest/jobs/{id}` — Job status

---

## Documentation

- **Swagger UI**: http://localhost:3000/api/docs (NestJS backend)
- **ReDoc**: http://localhost:3000/api/redoc

---

## WebSocket

**Streaming Server**: `ws://localhost:8082/ws`

Real-time candle updates (Go service). Connect for live chart data.
