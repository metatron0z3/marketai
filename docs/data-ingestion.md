# Data Ingestion Flow

## Overview

MarketAI ingests tick-level market data from Databento in `.dbn.zst` format and stores it in QuestDB for analysis and charting.

## Step-by-Step Flow

```
User uploads file
       │
       ▼
Frontend → NestJS (/api/v1/ingest/upload)
       │
       ▼
NestJS proxies → Python Service
       │
       ▼
Python decompresses .dbn.zst (Databento format)
       │
       ▼
Python parses tick records (trade, quote, ohlcv, etc.)
       │
       ▼
Python filters for supported symbols (SPY, QQQ, TSLA)
       │
       ▼
Python calculates indicator features (optional)
       │
       ▼
Python bulk-inserts into QuestDB via PostgreSQL wire
       │
       ▼
Job status available at /api/v1/ingest/jobs/{id}
```

## File Format Support

- **`.dbn.zst`** (primary): Databento compressed format — fast, efficient
- **`.zip`** (supported): Multiple .dbn files in archive

## Processing Steps

### 1. Decompression & Parsing

Python uses the `databento` SDK to:
- Decompress `.dbn.zst` files
- Parse records (trades, quotes, etc.)
- Map raw data to consistent schema

### 2. Filtering

Records are filtered by `instrument_id`:
- SPY (15144)
- QQQ (13340)
- TSLA (16244)

Unsupported symbols are dropped.

### 3. Insertion

Records inserted into QuestDB `trades_data` table via PostgreSQL wire protocol (port 8812):
- Batch inserts for performance
- Duplicate handling (by sequence number)
- Atomic transactions per batch

### 4. Job Status

Async job tracking returns status to client:
```json
{
  "job_id": "uuid-here",
  "status": "completed",
  "file": "data.dbn.zst",
  "records_inserted": 1250000,
  "duration_seconds": 45
}
```

## Configuration

Python service uses environment variables:
- `QUESTDB_HOST`: QuestDB hostname
- `QUESTDB_PORT`: PostgreSQL wire port (9000 for HTTP queries, 8812 for bulk insert)

See `@docs/environment.md` for details.

## Error Handling

If ingestion fails:
1. Check job status: `GET /api/v1/ingest/jobs/{id}`
2. Review Python logs: `docker-compose logs python-service`
3. Verify QuestDB is running: `docker-compose logs questdb`
4. Confirm file format is valid `.dbn.zst`

## Performance Tips

- Upload during off-market hours to avoid slowdowns
- For large files (>500MB), consider chunking
- Monitor QuestDB CPU/memory: http://localhost:9000
