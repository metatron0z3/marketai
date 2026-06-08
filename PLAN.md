# Multi-Agent Options Analysis — Implementation Plan

**Branch**: `multi_agentic_analysis`
**Goal**: Replace the single-threaded LLM enrichment loop with a coordinated multi-agent pipeline that analyzes, prepares, and queries data across the full ML stack — model-agnostic, cost-tracked, idempotent.

---

<!-- legacy content below — superseded by multi_agentic_analysis plan -->

## [Archive] Branch: `schema-change-massive`

All ML pipeline adaptation work is **complete**. The branch adapts the full pipeline
(ingest → labels → features → whale features) to support the Massive REST API path
alongside the original Databento path, using `data_source="massive"` / `"databento"`.

---

## Step 1 — Commit the uncommitted changes (do this first)

Two files have unstaged changes that belong on this branch:

```bash
git add python-service/app/modules/options/services/massive_ingest.py \
        python-service/cli/ingest_massive.py
git commit -m "feat: add rate-limit retry, timestamptz fix, and contract-type filter to Massive ingest"
```

**What's in these changes:**
- `massive_ingest.py` — `_PAGE_DELAY` env var, `_MAX_RETRIES=5`, `_do_get()` with 429
  retry loop honouring `Retry-After`, `_ts()` helper strips tzinfo for QuestDB
  compatibility, `contract_type` + `expiration_date_gte` params on `fetch_contracts()`
- `ingest_massive.py` (CLI) — `--contract-type` and `--no-expired` flags wired through,
  `expiration_date_gte=start_date` passed to `fetch_contracts()`

Do NOT commit: `ingest.log`, `nohup.out`, `run_all_ingests.sh`, `run_ingest.sh`,
`pr6-python-options-review.html` — these are runtime/scratch files.

---

## Step 2 — Push and open PR

```bash
git push origin schema-change-massive
```

Then open a PR: `schema-change-massive` → `main`

**PR summary to use:**
> Replaces the Databento/OPRA tick-data ingest path with Massive.com Options Basic Free
> REST API. Adds `data_source` param throughout the ML pipeline so both paths coexist.
> Free plan provides OHLCV aggregate bars only (no tick trades, no Greeks, no OI) —
> tick-only features are zero-filled on the Massive path.
>
> Changes:
> - New QuestDB tables: `options_bars`, `underlying_bars`, `options_contracts`, `options_ingest_runs`
> - `massive_ingest.py` service with rate-limit retry, 429 backoff, idempotent writes
> - `ingest_massive.py` CLI for direct ingestion runs
> - `data_source` param on `/features/compute`, `/whale/features/compute`, label services
> - `compute_features()` + `compute_whale_features()` read from `options_bars` on Massive path
> - 21 tests passing

---

## Step 3 — Verify data in QuestDB

Once the ingest has enough data (NVDA Q3 2025 calls in progress as of this writing),
run spot checks:

```sql
-- How many bars do we have?
SELECT underlying_symbol, contract_type, count() as bars
FROM options_bars
SAMPLE BY 1d ALIGN TO CALENDAR;

-- Which quarters are populated?
SELECT underlying_symbol, contract_type,
       min(ts_event) as first_bar, max(ts_event) as last_bar,
       count() as total_bars
FROM options_bars
GROUP BY underlying_symbol, contract_type;

-- Check ingest run history
SELECT underlying_symbol, start_date, end_date, contracts_ingested,
       bars_written, status, ts_finished
FROM options_ingest_runs
ORDER BY ts_started DESC;
```

QuestDB web console: http://localhost:9000

---

## Step 4 — Run the ML pipeline end-to-end on real data

With TSLA Q1+Q2+Q1-26 calls and NVDA Q1+Q2+Q3 calls available, test the full pipeline:

```python
# In python-service:
from app.modules.options.services.features import compute_features
from app.modules.options.services.whale_features import compute_whale_features
from app.modules.options.services.labels import compute_labels

# Test with a known good ticker/date
features = compute_features(
    ticker="O:TSLA250117C00250000",
    data_source="massive"
)
whale = compute_whale_features(
    underlying="TSLA",
    as_of_date="2025-01-17",
    data_source="massive"
)
```

Expected: features compute without error; tick-only fields (sweep_intensity,
aggressor_ratio, delta_exposure, iv_rank, vol_oi_ratio) will be 0.0 — that's correct.

---

## Step 5 — YouTube options trade data integration (separate repo)

The user has a separate repo collecting high-volume options trade data from a YouTube
channel. Format: JSON files with runup + aftermath context per trade.

**Goal:** Use this as validation/training signal for the whale detector.

**Integration approach to discuss:**
1. What's the JSON schema? (ticker, date, strike, expiry, direction, entry_price,
   peak_price, outcome?)
2. Map each trade onto `options_bars` rows by ticker + date range
3. The `compute_labels` framework already computes forward returns — the YouTube trades
   could serve as ground-truth "whale" labels for supervised training
4. Consider adding a `ground_truth_trades` table to QuestDB for these records

---

## Ingest status (as of 2026-05-24 ~1pm ET)

The overnight ingest is still running via `run_all_ingests.sh` (background process).

| Symbol | Quarter | Type | Status |
|--------|---------|------|--------|
| TSLA | Q1 2025 | call | ✅ Done |
| TSLA | Q2 2025 | call | ✅ Done (~1986 contracts) |
| TSLA | Q3 2025 | call | ❌ Failed — 0 contracts (rate limit); needs re-run |
| TSLA | Q4 2025 | call | ❌ Failed — 0 contracts (rate limit); needs re-run |
| TSLA | Q1 2026 | call | ✅ Done (~3366 contracts) |
| NVDA | Q1 2025 | call | ✅ Done (2275 contracts) |
| NVDA | Q2 2025 | call | ✅ Done (1774 contracts) |
| NVDA | Q3 2025 | call | 🔄 In progress (~22% at time of writing) |
| NVDA | Q4 2025 | call | ⏳ Pending (auto-starts after Q3) |
| NVDA | Q1 2026 | call | ✅ Done (2311 contracts) |
| TSLA | All quarters | put | ⏳ Not started |
| NVDA | All quarters | put | ⏳ Not started |

**Monitor:**
```bash
tail -20 /Users/maurice/Documents/Code/marketai/ingest.log
ps aux | grep ingest_massive | grep -v grep
```

**Re-run failed TSLA quarters after everything else settles:**
```bash
export MASSIVE_API_KEY=8DPzKWGuN9gqoME9trsHRPpeV283GJZY QUESTDB_HOST=localhost
python3 python-service/cli/ingest_massive.py --symbol TSLA --start 2025-07-01 --end 2025-09-30 --contract-type call
# wait for completion, then:
python3 python-service/cli/ingest_massive.py --symbol TSLA --start 2025-10-01 --end 2025-12-31 --contract-type call
```

---

## Key files

| File | Purpose |
|------|---------|
| `python-service/app/modules/options/services/massive_ingest.py` | Core ingest service |
| `python-service/cli/ingest_massive.py` | CLI runner |
| `python-service/app/modules/options/db/schema.py` | QuestDB table definitions |
| `python-service/app/modules/options/services/features.py` | Feature computation |
| `python-service/app/modules/options/services/whale_features.py` | Whale feature computation |
| `python-service/app/modules/options/services/labels.py` | Label computation |
| `python-service/tests/test_feature_data_source.py` | 21 tests, all passing |
| `run_all_ingests.sh` | Sequential ingest script (not committed, running now) |
