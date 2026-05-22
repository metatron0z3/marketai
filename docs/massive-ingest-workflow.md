# Massive Ingest Workflow

How to pull option contract + OHLCV bar data from the Massive REST API into QuestDB, and what happens to it afterward.

---

## What the script does

`python-service/cli/ingest_massive.py` runs the full Massive ingest pipeline in one shot:

1. **Discovers contracts** — calls `/v3/reference/options/contracts` for the underlying ticker, follows pagination, writes results to `options_contracts`
2. **Fetches option bars** — calls `/v2/aggs` for each contract, writes OHLCV bars to `options_bars`
3. **Fetches underlying bars** — same endpoint for the stock itself, window extended **+30 days** past your end date (so label generation has future price data without a separate ingest), writes to `underlying_bars`
4. **Logs the run** — writes a summary row to `options_ingest_runs` with status, counts, and timing

Inserts are idempotent: it checks existing timestamps before writing, so re-running the same date range is safe.

---

## Prerequisites

### 1. Set your API key

The script reads `MASSIVE_API_KEY` from the environment. Add it to a `.env` file in the repo root (already gitignored) or export it in your shell:

```bash
export MASSIVE_API_KEY=your_key_here
```

### 2. Stack must be running (for QuestDB)

```bash
docker-compose up -d questdb
```

QuestDB exposes its PostgreSQL wire protocol on `localhost:8812`. You do not need the python-service container running to use the CLI — you run the script directly on your host.

### 3. Python dependencies

The CLI imports from `app/`, so you need the service dependencies installed locally. From `python-service/`:

```bash
pip install requests psycopg2-binary
```

Or install everything:

```bash
pip install -r requirements.txt
```

---

## Running the script

All commands are run from `python-service/` with `QUESTDB_HOST=localhost` (the default when running outside Docker).

### Basic — daily bars, 100 contracts

```bash
cd python-service

MASSIVE_API_KEY=$MASSIVE_API_KEY \
  python cli/ingest_massive.py \
    --symbol SPY \
    --start 2025-01-01 \
    --end 2025-03-31
```

### Dry-run first (recommended before a large ingest)

Hits the Massive API and prints what would be written, but does not touch QuestDB. Use this to verify your API key works and see how many contracts and bars are available.

```bash
MASSIVE_API_KEY=$MASSIVE_API_KEY \
  python cli/ingest_massive.py \
    --symbol SPY \
    --start 2025-01-01 \
    --end 2025-03-31 \
    --dry-run
```

Example output:
```
[09:14:02] Massive ingest: SPY  2025-01-01 → 2025-03-31  resolution=1/day  max_contracts=100
[09:14:02] ingest_run_id: a3f1bc...
[09:14:03] Fetching contracts for SPY as_of=2025-03-31 ...
[09:14:04]   100 contracts discovered
  [1/100] O:SPY250117C00480000 (call 480.0 exp 2025-01-17): 17 bars (dry-run, not written)
  [2/100] O:SPY250117P00480000 (put  480.0 exp 2025-01-17): 17 bars (dry-run, not written)
  ...
[09:14:45] Fetching underlying bars for SPY 2025-01-01 → 2025-04-30 (+30d for label headroom)...
[09:14:45]   91 underlying bars (dry-run, not written)
[09:14:45] Done [completed] in 43.1s — contracts=100/100  option_bars=1632  underlying_bars=91
```

### More contracts

The default cap is 100. Raise it with `--max-contracts`:

```bash
MASSIVE_API_KEY=$MASSIVE_API_KEY \
  python cli/ingest_massive.py \
    --symbol SPY \
    --start 2025-01-01 \
    --end 2025-03-31 \
    --max-contracts 500
```

### Active contracts only (exclude expired)

By default the script includes expired contracts, which is what you want for historical training data. Pass `--no-expired` to limit to currently-active contracts only:

```bash
MASSIVE_API_KEY=$MASSIVE_API_KEY \
  python cli/ingest_massive.py \
    --symbol SPY \
    --start 2025-06-01 \
    --end 2025-06-30 \
    --no-expired
```

### Hourly bars

```bash
MASSIVE_API_KEY=$MASSIVE_API_KEY \
  python cli/ingest_massive.py \
    --symbol QQQ \
    --start 2025-06-01 \
    --end 2025-06-30 \
    --timespan hour
```

All options:

| Flag | Default | Description |
|------|---------|-------------|
| `--symbol` | required | Underlying ticker (SPY, QQQ, AAPL…) |
| `--start` | required | Bar start date, inclusive (YYYY-MM-DD) |
| `--end` | required | Bar end date, inclusive (YYYY-MM-DD) |
| `--timespan` | `day` | Bar resolution: `minute`, `hour`, `day`, `week`, `month` |
| `--multiplier` | `1` | Bar multiplier (e.g. `5` + `minute` = 5-minute bars) |
| `--max-contracts` | `100` | Contract cap (Massive free plan rate-limits large runs) |
| `--no-expired` | off | Exclude expired contracts |
| `--dry-run` | off | Fetch from API, print counts, do not write to QuestDB |

---

## Where the data lands

All data goes into QuestDB on `localhost:9000` (web console) / `localhost:8812` (PostgreSQL).

```
options_contracts     — one row per contract discovered (ticker, strike, expiration, type…)
options_bars          — OHLCV bars per option contract per time period
underlying_bars       — OHLCV bars for the underlying stock (SPY, QQQ…)
options_ingest_runs   — one row per CLI run with status, counts, start/end time
```

### Inspect the data

Open the QuestDB web console at **http://localhost:9000** and run:

```sql
-- What was ingested and when
SELECT * FROM options_ingest_runs ORDER BY ts_started DESC LIMIT 10;

-- Option bars for SPY calls expiring Jan 2025
SELECT * FROM options_bars
WHERE underlying_symbol = 'SPY'
  AND contract_type = 'call'
  AND expiration_date = '2025-01-17'
ORDER BY ts_event;

-- Underlying daily bars
SELECT * FROM underlying_bars
WHERE symbol = 'SPY'
ORDER BY ts_event;
```

Or connect with psql:

```bash
psql -h localhost -p 8812 -U admin -d qdb
```

---

## After ingest: running the ML pipeline

Once data is in QuestDB, the pipeline steps run via the Python service API (or directly as functions). With `data_source="massive"` they read from `options_bars` / `underlying_bars` instead of the legacy Databento tables.

```
1. ingest     → options_bars, underlying_bars       [CLI script above]
2. features   → options_features                    POST /api/v1/options/features/compute?data_source=massive
3. labels     → options_features.label_24h          POST /api/v1/options/labels/generate?data_source=massive
4. whale feat → whale_features                      POST /api/v1/whale/features/compute?data_source=massive
5. whale lbls → whale_features.label_4w             POST /api/v1/whale/labels/generate?data_source=massive
6. train      → model artifacts in MLflow
7. inference  → POST /api/v1/whale/predict
```

Example full pipeline run for SPY after ingest:

```bash
BASE=http://localhost:8000/api/v1
SYM=SPY
START=2025-01-01
END=2025-03-31

curl -X POST "$BASE/options/features/compute?symbol=$SYM&start_date=$START&end_date=$END&data_source=massive"
curl -X POST "$BASE/options/labels/generate?symbol=$SYM&start_date=$START&end_date=$END&data_source=massive"
curl -X POST "$BASE/whale/features/compute?symbol=$SYM&start_date=$START&end_date=$END&data_source=massive"
curl -X POST "$BASE/whale/labels/generate?symbol=$SYM&start_date=$START&end_date=$END&data_source=massive"
```

---

## Note on Docker

The CLI runs on your **host machine** against a locally-exposed QuestDB (`localhost:8812`). It does not run inside a container.

The `python-service` Dockerfile only copies `app/` — the `cli/` folder is intentionally excluded from the production image since it's a dev/ops tool, not part of the API server. If you ever need to run the script inside Docker (e.g. in CI), use a bind mount:

```bash
docker run --rm \
  -e MASSIVE_API_KEY=$MASSIVE_API_KEY \
  -e QUESTDB_HOST=questdb \
  -v $(pwd)/python-service/cli:/app/cli \
  --network marketai_market_network \
  market_python_service \
  python cli/ingest_massive.py --symbol SPY --start 2025-01-01 --end 2025-03-31
```

The Docker network name is `marketai_market_network` (compose project name prefix + network name from docker-compose.yml).
