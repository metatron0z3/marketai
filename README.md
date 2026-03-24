# MarketAI

A real-time market data platform with technical analysis capabilities. Built with **NestJS**, **Python**, **Go**, **Angular**, and **QuestDB**. Features high-frequency tick-level data ingestion, OHLCV aggregation, technical indicators (RSI, VWAP, Moving Averages, Bollinger Bands), and live WebSocket streaming.

---

## Architecture

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
│ - Instruments   │ │ - WebSocket   │ │ - Data Ingest   │
│ - Market Data   │ │ - Live Charts │ │ - Indicators    │
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

---

## Services

| Service | Language | Port | Responsibilities |
|---------|----------|------|------------------|
| **Frontend** | Angular | 4200 | Web UI, charting, indicator toggles |
| **NestJS Backend** | TypeScript | 3000 | API gateway, market data, indicators, orchestration |
| **Python Service** | Python | 8000 | Data ingestion (.dbn.zst), feature engineering, ML models |
| **Streaming (Go)** | Go | 8082 | WebSocket streaming, live chart updates |
| **QuestDB** | Java | 9000/8812 | Time-series database, OHLCV aggregations |

---

## Features

### 📊 Market Data
- **Tick-level ingestion** from Databento (.dbn.zst files)
- **Symbols supported**: SPY (15144), QQQ (13340), TSLA (16244)
- **OHLCV aggregation** at 5min, 1hour, 1day intervals
- **Time-series database** with per-day partitioning

### 📈 Technical Indicators
All indicators are **independently toggleable** on the frontend:

| Indicator | Calculation | Display |
|-----------|-------------|---------|
| **RSI** | 14-period Wilder's smoothing | Separate chart panel (0-100 scale) |
| **VWAP** | Volume-weighted average price | Blue line overlay on price chart |
| **MA7** | 7-period simple moving average | Yellow line overlay |
| **MA20** | 20-period simple moving average | Cyan line overlay |
| **MA200** | 200-period simple moving average | Red line overlay |
| **Bollinger Bands** | 20-period ±2σ | 3-line overlay (upper/middle/lower) |
| **Volume** | Per-candle volume bars | Histogram at bottom of chart |

### 🔄 Real-time Streaming
- **WebSocket API** at `ws://localhost:8082/ws`
- Live candlestick updates
- Auto-reconnect on disconnect

### 🛠️ Support/Resistance Lines
- Draw custom S/R levels on chart
- Click to add, right-click to delete
- Persistent storage (file-based JSON + localStorage fallback)

---

## Quick Start

### Prerequisites
- **Docker Desktop** (check: `docker info`)
- **Git** (check: `git --version`)
- **System resources**: ~2GB RAM, 500MB free disk space

### Launch All Services

```bash
# Clone and navigate
git clone https://github.com/metatron0z3/marketai.git
cd marketai

# Start all containers (builds on first run)
docker-compose up --build

# Wait ~30-40 seconds for services to initialize
```

**Services will be available at:**
- 🌐 **Frontend**: http://localhost:4200
- 🔌 **NestJS API**: http://localhost:3000
- 📚 **Swagger Docs**: http://localhost:3000/api/docs
- 🐍 **Python Service**: http://localhost:8000 (internal)
- 📊 **QuestDB Console**: http://localhost:9000 (user: `admin`, password: `quest`)
- 🟢 **WebSocket (Go)**: ws://localhost:8082/ws

---

## Frontend Workflow

### 1. Market Data View (Primary)
**Route:** `http://localhost:4200/market-data`

**Controls:**
- **Instrument dropdown**: Select SPY, QQQ, or TSLA
- **Timeframe dropdown**: 5min, 1hour, 1day
- **Date range**: Start and end dates
- **Pull Data button**: Fetch market data from QuestDB
- **S/R Lines toggle**: Show/hide custom support/resistance lines
- **Indicator toggles**: RSI, VWAP, MA200, MA20, MA7, Bollinger, Volume

**Workflow:**
1. Select an instrument and date range
2. Click "Pull Data" to load OHLCV candles
3. Toggle indicators to visualize them on the chart
4. Zoom/pan the chart with mouse
5. Draw S/R lines: double-click to add, right-click to delete
6. Toggle off indicators to clean up the view

### 2. Data Ingestion (Upload)
**Route:** `http://localhost:4200/ingest`

**Upload .dbn.zst files:**
1. Click "Choose File" and select a `.dbn.zst` or `.zip` file
2. Click "Upload and Ingest"
3. Monitor progress bar
4. Check "Ingestion Jobs" for details

### 3. Data Ranges
**Route:** `http://localhost:4200/data-ranges`

View available date ranges per symbol to know what data is loaded.

### 4. Live Streaming
**Route:** `http://localhost:4200/animated-chart`

Real-time candlestick updates via WebSocket (Go streaming service).

---

## API Documentation

### NestJS Backend Routes

**Base URL:** `http://localhost:3000/api/v1`

#### Instruments
```
GET  /instruments/           → List all instruments
GET  /instruments/:symbol    → Get instrument by symbol
```

#### Market Data
```
GET  /market-data?instrument_id=15144&timeframe=5min&start_date=2024-01-02&end_date=2024-01-05
```

#### Indicators
```
GET  /indicators/rsi?instrument_id=15144&timeframe=5min&start_date=2024-01-02&end_date=2024-01-05
GET  /indicators/vwap?instrument_id=15144&timeframe=5min&start_date=2024-01-02&end_date=2024-01-05
GET  /indicators/ma200?instrument_id=15144&timeframe=5min&start_date=2024-01-02&end_date=2024-01-05
GET  /indicators/ma20?instrument_id=15144&timeframe=5min&start_date=2024-01-02&end_date=2024-01-05
GET  /indicators/ma7?instrument_id=15144&timeframe=5min&start_date=2024-01-02&end_date=2024-01-05
GET  /indicators/bollinger-bands?instrument_id=15144&timeframe=5min&start_date=2024-01-02&end_date=2024-01-05
GET  /indicators/volume?instrument_id=15144&timeframe=5min&start_date=2024-01-02&end_date=2024-01-05
```

**Response shape** (example: RSI):
```json
{
  "meta": {
    "instrument_id": 15144,
    "timeframe": "5min",
    "period": 14,
    "insufficient_data": false
  },
  "data": [
    { "timestamp": "2024-01-02T09:30:00Z", "rsi": 58.32 },
    { "timestamp": "2024-01-02T09:35:00Z", "rsi": 62.15 }
  ]
}
```

#### Ingestion
```
POST /ingest/upload           → Upload .dbn.zst file
GET  /ingest/jobs            → List all ingestion jobs
GET  /ingest/jobs/:jobId     → Get job status
```

#### Support/Resistance
```
GET  /support-resistance      → Get all S/R lines (by symbol)
POST /support-resistance      → Save all S/R lines
```

**Full Swagger documentation:** http://localhost:3000/api/docs

---

## Development Workflow

### Code Structure

```
marketai/
├── frontend/                          # Angular app
│   ├── src/app/
│   │   ├── pages/market-data/        # Main chart page
│   │   ├── components/chart/         # Candlestick chart + overlays
│   │   ├── core/services/            # HTTP + WebSocket services
│   │   └── app.routes.ts             # Route definitions
│   └── Dockerfile
│
├── backend-nest/                      # NestJS API
│   ├── src/
│   │   ├── modules/
│   │   │   ├── instruments/          # Instrument data
│   │   │   ├── market-data/          # OHLCV aggregations
│   │   │   ├── indicators/           # Technical indicators (NEW)
│   │   │   ├── ingest/               # File upload proxy
│   │   │   └── support-resistance/   # S/R line storage
│   │   ├── database/                 # QuestDB connection pool
│   │   └── main.ts                   # App entry
│   └── Dockerfile
│
├── python-service/                    # FastAPI app
│   ├── app/
│   │   ├── api/v1/
│   │   │   ├── endpoints/
│   │   │   │   ├── indicators.py     # 7 indicator endpoints (NEW)
│   │   │   │   ├── ingest.py         # File processing
│   │   │   │   └── market_data.py    # OHLCV query
│   │   │   └── api.py
│   │   ├── services/
│   │   │   ├── ohlcv.py              # Shared OHLCV fetch (NEW)
│   │   │   └── indicators.py         # Pandas calculations (NEW)
│   │   ├── core/db.py                # QuestDB psycopg2 connection
│   │   └── main.py                   # FastAPI app
│   └── Dockerfile
│
├── streaming/                         # Go WebSocket server
│   ├── main.go
│   ├── go.mod
│   └── Dockerfile
│
├── docker-compose.yml                 # Service orchestration
└── README.md                          # This file
```

### Make Code Changes

1. **Edit files** in your IDE
2. **Rebuild affected service(s)**:
   ```bash
   # Frontend
   docker-compose up --build frontend

   # NestJS backend
   docker-compose up --build nestjs-backend

   # Python service
   docker-compose up --build python-service

   # All services
   docker-compose up --build
   ```

3. **View logs**:
   ```bash
   docker-compose logs -f [service-name]
   ```

### Git Workflow (Feature Branches)

```bash
# Create feature branch
git checkout -b feature/your-feature-name

# Make changes and commit
git add .
git commit -m "feat: description of changes"

# Push to GitHub
git push -u origin feature/your-feature-name

# Create pull request on GitHub UI
```

**Current branches:**
- `main` — Production-ready
- `staging` — Integration branch
- `feature-indicators` — Technical indicators feature (merged)

---

## Common Tasks

### View Chart in Browser
```bash
open http://localhost:4200
```

### Check Service Logs
```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f nestjs-backend
docker-compose logs -f python-service
docker-compose logs -f frontend
```

### Query QuestDB Directly
```bash
# Web console
open http://localhost:9000

# Or via psql
psql -h localhost -p 8812 -U admin -d qdb
# Password: quest

# Sample queries
SELECT COUNT(*) FROM trades_data;
SELECT DISTINCT instrument_id FROM trades_data;
SELECT ts_event, price, size FROM trades_data WHERE instrument_id = 15144 LIMIT 10;
```

### Restart Services
```bash
# Graceful restart
docker-compose restart

# Full rebuild
docker-compose down
docker-compose up --build
```

### Clear Data and Start Fresh
```bash
# Stop containers and remove volumes
docker-compose down -v

# Restart (rebuilds images, creates fresh DB)
docker-compose up --build
```

---

## Troubleshooting

### Frontend Not Loading
```bash
# Check if container is running
docker ps | grep frontend

# View logs
docker-compose logs frontend

# Rebuild
docker-compose up --build frontend
```

### NestJS API Errors
```bash
# Check if backend is running
curl http://localhost:3000/health

# View logs
docker-compose logs nestjs-backend

# Full rebuild
docker-compose down nestjs-backend
docker-compose up --build nestjs-backend
```

### Indicator Data Not Showing
1. Pull market data first (click "Pull Data" button)
2. Toggle the indicator button
3. Check browser console for errors (F12)
4. Verify indicator endpoint: `curl http://localhost:3000/api/v1/indicators/rsi?instrument_id=15144`

### QuestDB Connection Issues
```bash
# Verify QuestDB is running
docker ps | grep questdb

# Test connection
psql -h localhost -p 8812 -U admin -d qdb

# Check for data
psql -h localhost -p 8812 -U admin -d qdb
> SELECT COUNT(*) FROM trades_data;

# If empty, upload a file via the frontend at http://localhost:4200/ingest
```

### WebSocket Connection Fails (Live Chart)
```bash
# Check Go streaming service
docker ps | grep streaming

# View logs
docker-compose logs streaming

# Test WebSocket
curl -i -N -H "Connection: Upgrade" -H "Upgrade: websocket" http://localhost:8082/ws
```

### Memory Issues
```bash
# Check available RAM
free -h          # Linux
vm_stat | grep "Pages free"  # macOS

# Reduce chart history in frontend (edit market-data.ts)
# Or restart with fewer services
docker-compose up questdb nestjs-backend
```

---

## References

- **QuestDB Documentation**: https://questdb.io/docs/
- **Databento API**: https://databento.com/docs/
- **NestJS Documentation**: https://docs.nestjs.com/
- **Lightweight Charts**: https://tradingview.github.io/lightweight-charts/
- **Angular Documentation**: https://angular.io/docs

---

## Recent Changes (Latest Branch: `feature-indicators`)

### ✨ New Features
- **7 Technical Indicators**: RSI, VWAP, MA7, MA20, MA200, Bollinger Bands, Volume
- **Indicator Toggle Panel**: Independent on/off toggles on Market Data page
- **Smart Data Fetching**: Auto-fetch indicators when toggled or when pulling data
- **Multi-chart Display**: RSI as separate 120px sub-chart, others as line overlays

### 📦 API Additions
- `GET /api/v1/indicators/rsi` — RSI 14-period
- `GET /api/v1/indicators/vwap` — Volume-weighted average price
- `GET /api/v1/indicators/ma200` — 200-period moving average
- `GET /api/v1/indicators/ma20` — 20-period moving average
- `GET /api/v1/indicators/ma7` — 7-period moving average
- `GET /api/v1/indicators/bollinger-bands` — Bollinger Bands 20/2σ
- `GET /api/v1/indicators/volume` — Per-candle volume

### 🎨 Frontend Enhancements
- Color-coded indicator toggle buttons (match series colors)
- Responsive indicator panel in controls bar
- Lightweight-charts series management for dynamic indicator rendering

---

## License

MarketAI is open source and available under the MIT License.

---

**Last Updated**: March 2026
**Latest Branch**: `feature-indicators`
**Deploy Status**: Docker Compose ready
