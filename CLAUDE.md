# CLAUDE.md - MarketAI Development Guide

This document provides architecture context and development guidance for Claude Code instances working with the MarketAI repository.

## Project Purpose

MarketAI is a Python-based pipeline for ingesting, storing, analyzing, and visualizing tick-by-tick (TBBO - Top of Book Best Bid/Offer) market data from Databento. The system is designed to:

- Ingest compressed market data files (.dbn.zst format) from Databento
- Store tick data in QuestDB, a high-performance time-series database
- Engineer trading features from raw tick data
- Visualize market microstructure through a Streamlit dashboard

**Key Technologies:**
- Python 3.12
- QuestDB (time-series database)
- Docker & Docker Compose
- Databento (market data provider)
- Streamlit (visualization)
- psycopg2 (PostgreSQL wire protocol)

## Architecture Overview

### Data Flow
```
Databento .dbn.zst files → Ingest Service → QuestDB → Feature Engineering
                                                    ↓
                                              Streamlit Dashboard
```

### Service Architecture (Docker Compose)

The application runs three services orchestrated by Docker Compose:

1. **questdb** - Time-series database
   - Ports: 9000 (HTTP/Web Console), 8812 (PostgreSQL wire), 9009 (ILP)
   - Web Console: http://localhost:9000 (admin/quest)
   - Volume: `questdb-data` for persistence
   - Network: `market_network`

2. **ingest** - Data ingestion service
   - Built from Dockerfile
   - Mounts: ./data → /data, ./src → /src
   - Depends on: questdb
   - Environment: QUESTDB_HOST=questdb

3. **streamlit** - Visualization dashboard
   - Port: 8501
   - Mounts: ./src → /src
   - Depends on: questdb
   - Environment: QUESTDB_HOST=questdb, QUESTDB_PORT=8812

### Database Schema

**Table: `trades_data`**
- Primary timestamp column: `ts_event` (designated timestamp)
- Partition strategy: `PARTITION BY DAY` on `ts_event`
- Schema includes: instrument_id, action, side, price, size, flags, ts_recv, ts_in_delta, sequence

**Symbol Mapping:**
- SPY: instrument_id = 15144
- QQQ: instrument_id = 13340
- TSLA: instrument_id = 16244

### Connection Protocols

QuestDB supports multiple protocols - this project uses two:

1. **HTTP API (port 9000)** - Used by ingest_cli.py for bulk data insertion and by Streamlit dashboard for data queries
2. **PostgreSQL wire protocol (port 8812)** - Used by feature_engineering.py via psycopg2

## Common Development Commands

### Docker Operations

```bash
# Start all services (build if needed)
docker-compose up --build

# Start services in detached mode
docker-compose up -d

# Stop all services
docker-compose down

# Force rebuild without cache
docker-compose build --no-cache

# View logs from all services
docker-compose logs

# View logs from specific service
docker-compose logs questdb
docker-compose logs ingest
docker-compose logs streamlit

# Execute commands in running container
docker-compose exec questdb /bin/bash
docker-compose exec ingest /bin/bash
```

### Ingest CLI Commands

The ingest CLI (`src/ingest_cli.py`) provides commands for data ingestion:

```bash
# Test database connection
python ingest_cli.py test-connection

# Create the trades_data table
python ingest_cli.py create-table

# List available .dbn.zst files
python ingest_cli.py list-files

# Process a specific file
python ingest_cli.py process-file <filename>

# Process all files in data directory
python ingest_cli.py process-all

# Process with custom batch size
python ingest_cli.py process-file <filename> --batch-size 100
```

### Local Development Setup

```bash
# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run Streamlit locally
streamlit run src/market_view_day.py
```

### QuestDB Access

**Web Console:**
- URL: http://localhost:9000
- Credentials: admin / quest
- Use for: SQL queries, table inspection, system monitoring

**PostgreSQL Wire Protocol:**
- Host: localhost
- Port: 8812
- User: admin
- Password: quest
- Use for: psycopg2 connections, feature engineering, analytics

**Example psycopg2 connection:**
```python
import psycopg2
conn = psycopg2.connect(
    host='localhost',
    port=8812,
    user='admin',
    password='quest',
    database='qdb'
)
```

## Key Implementation Details

### Data Format & Processing

**Databento Files:**
- Format: `.dbn.zst` (Zstandard compressed binary format)
- Location: `./data/` directory (mounted to `/data` in containers)
- Decompression: Handled automatically by `databento` Python library

**Data Transformations:**
- **Price scaling**: Divide raw price values by 1e9 to get decimal prices
- **Timestamp scaling**: Divide by 1000 to convert from nanoseconds to milliseconds
- **Batch processing**: Default batch size is 50 records (configurable via --batch-size)

**Ingestion Process:**
1. Open .dbn.zst file using databento library
2. Iterate through records in batches
3. Transform prices and timestamps
4. Map instrument_id to symbols
5. Insert batches via QuestDB HTTP API

### Feature Engineering

**Implementation:** `src/feature_engineering.py`

**Main Class:** `TradingFeatureEngineer`
- Connects via psycopg2 on port 8812
- Processes data from `trades_data` table
- Creates 6 feature tables with engineered features

**Generated Feature Tables:**
1. `price_features` - Price-based metrics (returns, volatility, spread)
2. `volume_features` - Volume analysis (VWAP, volume ratios)
3. `microstructure_features` - Market microstructure (effective spread, order flow imbalance)
4. `technical_features` - Technical indicators (RSI, Bollinger Bands, moving averages)
5. `advanced_features` - Advanced metrics (intraday returns, volume profiles)
6. `support_resistance_levels` - Price levels and volume clusters

**Usage Pattern:**
```python
engineer = TradingFeatureEngineer(
    host='localhost',
    port=8812,
    user='admin',
    password='quest'
)
engineer.create_all_features(symbol='SPY', date='2024-01-02')
```

### Streamlit Dashboard

**Implementation:** `src/market_view_day.py`

**Key Features:**
- Date and symbol selector in sidebar
- Interactive candlestick charts with 5-minute OHLC candles
- Data summary metrics (total trades, price range, volume)
- Real-time data fetching from QuestDB via HTTP API
- Default demo date: 2024-01-02

**Symbol Configuration:**
The dashboard uses the symbol mapping defined at module level:
```python
SYMBOL_MAP = {
    'SPY': 15144,
    'QQQ': 13340,
    'TSLA': 16244
}
```

**Environment Variables:**
- `QUESTDB_HOST` - QuestDB hostname (default: questdb in Docker, localhost for local development)
- `QUESTDB_PORT` - HTTP API port (default: 9000)

**Connection Pattern:**
The dashboard uses the HTTP API via the requests library:
```python
QUESTDB_HOST = os.getenv("QUESTDB_HOST", "questdb")
QUESTDB_PORT = os.getenv("QUESTDB_PORT", "9000")
QUESTDB_URL = f"http://{QUESTDB_HOST}:{QUESTDB_PORT}/exec"

response = requests.get(QUESTDB_URL, params={"query": query})
```

### File Structure

```
marketai/
├── docker-compose.yml       # Service orchestration
├── Dockerfile              # Container build config
├── requirements.txt        # Python dependencies
├── data/                   # .dbn.zst data files
├── cli/
│   └── questdb_cmds       # QuestDB CLI helpers
└── src/
    ├── ingest_cli.py      # Main ingestion CLI (398 LOC)
    ├── feature_engineering.py  # Feature pipeline (491 LOC)
    ├── market_view_day.py # Streamlit dashboard (222 LOC)
    ├── ml_pipeline.py     # Machine learning pipeline
    └── feature_advanced   # Advanced feature modules
```

## Important Conventions & Patterns

### Configuration Defaults
- **Batch size**: 50 records (configurable via --batch-size flag)
- **Docker network**: `market_network` (defined in docker-compose.yml)
- **QuestDB volume**: `questdb-data` (persistent storage)
- **Data mount**: `./data` → `/data` in containers

### Database Best Practices
- Always use `ts_event` as the designated timestamp for queries
- Leverage `PARTITION BY DAY` when querying specific dates
- Use batch inserts for performance (HTTP API supports bulk operations)
- PostgreSQL wire protocol is preferred for complex queries and analytics

### Development Workflow
1. Start services: `docker-compose up --build`
2. Verify QuestDB: http://localhost:9000
3. Create table: `python ingest_cli.py create-table`
4. Ingest data: `python ingest_cli.py process-all`
5. Generate features: Run feature_engineering.py
6. View dashboard: http://localhost:8501

### Common Troubleshooting

**QuestDB connection issues:**
- Check if QuestDB container is running: `docker-compose ps`
- Verify ports are not in use: `lsof -i :9000` or `lsof -i :8812`
- Check logs: `docker-compose logs questdb`

**Data ingestion errors:**
- Verify .dbn.zst files exist in ./data directory
- Check file permissions
- Verify table schema matches expected format
- Review batch size if memory issues occur

**Streamlit display issues:**
- Ensure data exists for selected date and symbol
- Check QuestDB connection from Streamlit container
- Verify feature tables have been created

## Development Tips

### Adding New Symbols
1. Identify instrument_id from Databento data
2. Update `SYMBOL_MAP` in market_view_day.py
3. Update documentation with new mapping

### Modifying Database Schema
1. Drop existing table: `DROP TABLE trades_data;`
2. Update CREATE TABLE statement in ingest_cli.py
3. Run: `python ingest_cli.py create-table`
4. Re-ingest data

### Performance Optimization
- QuestDB performs best with batched inserts (50-100 records)
- Use date filters in queries to leverage partitioning
- Index frequently queried columns (instrument_id)
- Monitor QuestDB logs for slow queries

### Testing Connection Flow
```bash
# 1. Test QuestDB HTTP API
curl http://localhost:9000/

# 2. Test from ingest container
docker-compose exec ingest python ingest_cli.py test-connection

# 3. Test PostgreSQL wire from host
psql -h localhost -p 8812 -U admin -d qdb
```

## Related Documentation
- QuestDB Documentation: https://questdb.io/docs/
- Databento API: https://databento.com/docs/
- Project README: ./README.md
