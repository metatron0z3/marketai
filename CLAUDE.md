# CLAUDE.md - MarketAI Development Guide

This document provides architecture context and development guidance for Claude Code instances working with the MarketAI repository.

## Skills

Before starting any task, check the `skills/` directory and load the relevant SKILL.md.
- Use `skills/orchestrator/SKILL.md` for any multi-step or cross-service task.
- Use the appropriate specialist skill for domain-specific work.
- See `skills/orchestrator/SKILL.md` for the full routing table.

## Project Status - Architecture Overview

**Current Date:** 2026-01-25
**Branch:** feature/nestjs-migration

### Current Architecture

```
                    ┌─────────────────┐
                    │  Angular FE     │
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
│ - Instruments   │ │ - Live Charts │ │ - databento     │
│ - Orchestration │ │               │ │ - ML Pipeline   │
└────────┬────────┘ └───────────────┘ └────────┬────────┘
         │                                      │
         └──────────────┬───────────────────────┘
                        ▼
              ┌─────────────────┐
              │    QuestDB      │
              │ (9000/8812)     │
              └─────────────────┘
```

### Service Responsibilities

| Service | Language | Port | Responsibilities |
|---------|----------|------|------------------|
| **nestjs-backend** | TypeScript | 3000 | API gateway, market data, instruments, service orchestration |
| **python-service** | Python | 8000 | Data ingestion (.dbn.zst), ML pipeline, feature engineering |
| **streaming** | Go | 8082 | WebSocket streaming, live chart data |
| **questdb** | - | 9000/8812 | Time-series database |
| **frontend** | Angular | 4200 | Web UI, charting |

### Why This Architecture?

1. **NestJS as API Gateway**: Handles client requests, orchestrates services, provides type-safe API
2. **Python for Data Science**: databento library, pandas, ML models - Python ecosystem is unmatched
3. **Go for Streaming**: High-performance WebSocket handling, low latency
4. **QuestDB**: Purpose-built time-series database for market data

---

## NestJS Backend Structure

```
backend-nest/
├── src/
│   ├── main.ts                 # Application entry point
│   ├── app.module.ts           # Root module
│   ├── app.controller.ts       # Root controller (health, db-status)
│   ├── app.service.ts          # Root service
│   ├── config/
│   │   └── configuration.ts    # Environment config
│   ├── database/
│   │   ├── database.module.ts  # Database module
│   │   └── questdb.service.ts  # QuestDB connection pool
│   └── modules/
│       ├── instruments/
│       │   ├── instruments.module.ts
│       │   ├── instruments.controller.ts
│       │   ├── instruments.service.ts
│       │   └── dto/instrument.dto.ts
│       ├── market-data/
│       │   ├── market-data.module.ts
│       │   ├── market-data.controller.ts
│       │   ├── market-data.service.ts
│       │   └── dto/
│       │       ├── market-data-query.dto.ts
│       │       └── ohlcv.dto.ts
│       └── ingest/
│           ├── ingest.module.ts
│           ├── ingest.controller.ts  # Proxies to Python service
│           ├── ingest.service.ts
│           └── dto/ingest.dto.ts
├── package.json
├── tsconfig.json
├── nest-cli.json
└── Dockerfile
```

---

## Python Service Structure

The Python service handles tasks requiring the Python data science ecosystem:

```
python-service/
├── app/
│   ├── main.py                 # FastAPI entry
│   ├── api/
│   │   └── v1/
│   │       ├── api.py          # Router setup
│   │       └── endpoints/
│   │           ├── instruments.py  # (deprecated, use NestJS)
│   │           ├── market_data.py  # (deprecated, use NestJS)
│   │           └── ingest.py       # File upload & processing
│   ├── core/
│   │   └── db.py               # QuestDB connection
│   └── models/
│       └── static_data/        # Static data files
└── requirements.txt
```

**Active Endpoints (Python Service):**
- `POST /api/v1/ingest/upload` - Upload .dbn.zst files
- `GET /api/v1/ingest/jobs` - List ingest jobs
- `GET /api/v1/ingest/jobs/{id}` - Job status

---

## Database Schema

**Table: `trades_data`**
```sql
CREATE TABLE IF NOT EXISTS trades_data (
    ts_recv TIMESTAMP,
    ts_event TIMESTAMP,
    rtype INT,
    publisher_id INT,
    instrument_id INT,
    action SYMBOL,
    side SYMBOL,
    depth INT,
    price DOUBLE,
    size LONG,
    flags INT,
    ts_in_delta LONG,
    sequence LONG
) TIMESTAMP(ts_event) PARTITION BY DAY;
```

**Symbol Mapping:**
| Symbol | instrument_id |
|--------|---------------|
| SPY    | 15144         |
| QQQ    | 13340         |
| TSLA   | 16244         |

---

## Docker Compose Services

```yaml
services:
  questdb:
    image: questdb/questdb:latest
    ports:
      - "9000:9000"   # HTTP API
      - "8812:8812"   # PostgreSQL wire

  nestjs-backend:
    build: ./backend-nest
    ports:
      - "3000:3000"
    environment:
      - QUESTDB_HOST=questdb
      - QUESTDB_PORT=8812
      - PYTHON_SERVICE_URL=http://python-service:8000

  python-service:
    dockerfile: Dockerfile.python-service
    ports:
      - "8000:8000"
    environment:
      - QUESTDB_HOST=questdb
      - QUESTDB_PORT=9000

  streaming:
    build: ./streaming
    ports:
      - "8082:8082"

  frontend:
    build: ./frontend
    ports:
      - "4200:80"
```

---

## Common Commands

### Docker Operations
```bash
# Start all services
docker-compose up --build

# Rebuild specific service
docker-compose build nestjs-backend

# View logs
docker-compose logs -f nestjs-backend
docker-compose logs -f python-service

# Shell into container
docker-compose exec nestjs-backend sh
```

### NestJS Development
```bash
cd backend-nest

# Install dependencies
npm install

# Run in development
npm run start:dev

# Build for production
npm run build

# Run tests
npm run test
```

### QuestDB Access
- Web Console: http://localhost:9000
- PostgreSQL: `psql -h localhost -p 8812 -U admin -d qdb`

---

## API Routes

### NestJS Backend (Port 3000)
| Method | Route | Description |
|--------|-------|-------------|
| GET | / | Welcome message |
| GET | /health | Health check |
| GET | /db-status | Database connection status |
| GET | /api/v1/instruments | List all instruments |
| GET | /api/v1/instruments/:symbol | Get instrument by symbol |
| GET | /api/v1/market-data | Get OHLCV data (query params: instrument_id, timeframe, start_date, end_date) |
| POST | /api/v1/ingest/upload | Proxy to Python service |
| GET | /api/v1/ingest/jobs | Proxy to Python service |
| GET | /api/v1/ingest/jobs/:id | Proxy to Python service |

### Swagger Documentation
- Available at: http://localhost:3000/api/docs

---

## Environment Variables

### NestJS Backend
```env
NODE_ENV=development
PORT=3000
QUESTDB_HOST=questdb
QUESTDB_PORT=8812
QUESTDB_USER=admin
QUESTDB_PASSWORD=quest
QUESTDB_DATABASE=qdb
PYTHON_SERVICE_URL=http://python-service:8000
```

### Python Service
```env
QUESTDB_HOST=questdb
QUESTDB_PORT=9000
```

---

## Frontend Configuration

### API Base URL
The frontend connects to the NestJS backend:
```typescript
// frontend/src/app/core/environment.ts
export const API_BASE_URL = 'http://localhost:3000/api/v1';
```

### Nginx Proxy (Production)
The nginx config proxies `/api/` to the NestJS backend:
```nginx
location /api/ {
    proxy_pass http://nestjs-backend:3000;
}
```

---

## Access URLs

| Service | URL |
|---------|-----|
| Frontend | http://localhost:4200 |
| NestJS API | http://localhost:3000 |
| Swagger Docs | http://localhost:3000/api/docs |
| Python Service | http://localhost:8000 (internal) |
| QuestDB Console | http://localhost:9000 |
| Live Chart WS | ws://localhost:8082/ws |

---

## Data Ingestion Flow

1. User uploads `.dbn.zst` or `.zip` file via frontend
2. Frontend sends to NestJS backend (`POST /api/v1/ingest/upload`)
3. NestJS proxies request to Python service
4. Python service processes file using `databento` library
5. Records inserted into QuestDB via PostgreSQL wire protocol
6. Job status available via polling `/api/v1/ingest/jobs/{id}`

---

## Development Workflow

1. Start services: `docker-compose up --build`
2. Verify QuestDB: http://localhost:9000
3. Verify NestJS: http://localhost:3000/health
4. View frontend: http://localhost:4200
5. Check API docs: http://localhost:3000/api/docs

---

## Related Documentation
- QuestDB Documentation: https://questdb.io/docs/
- Databento API: https://databento.com/docs/
- NestJS Documentation: https://docs.nestjs.com/
