# Prefect Orchestration Plan — TOS Data Collection

**Objective:** Automate all data collection from the Schwab/TOS API, store it in the
TOS databases (QuestDB + Postgres), and feed MarketAI's ML pipeline with a continuous
stream of labeled training data and live signals.

**State:** API key not yet live. This plan is ready to execute the moment it is.

---

## Why Prefect?

MarketAI already runs Prefect (port 4200). The TOS collector registers its flows with
the **same Prefect server** — no separate orchestration infrastructure needed. The TOS
collector is just another set of Prefect deployments pointing at the shared server.

The existing nightly retrain + scoring flows in `python-service/app/modules/tos/flows/`
become the downstream consumers of what this collector produces.

---

## Data Priority Tiers

The order matters because each tier unlocks the next. You cannot train models without
labeled events, and you cannot label events without both signals AND price history.

---

### TIER 1 — Unlock Training (must have before any model can run)

#### 1.1 Underlying Price History — OHLCV Daily + 1h Bars

**Why first:** Every label in `signal_catalog` is computed from underlying price
movement after the event. No price history → no labels → no training data. Period.

This is also the fastest data to collect: 12 tickers × 2 years ≈ ~6,000 API calls,
completable in under 20 minutes even with rate limiting.

**What to pull:**
- Daily OHLCV going back 2 years for all 12 tickers (for 20d moving averages, RSI, HV)
- 1-hour bars going back 6 months (for intraday RSI at event time)

**Features unlocked:** `underlying_return_1d/5d/20d`, `underlying_rsi_14`,
`underlying_vol_ratio_20d`, `hv_20d` (needed for `iv_vs_hv_ratio`)

**Labels unlocked:** `underlying_return_1d_fwd`, `underlying_return_5d_fwd`,
`direction_correct_5d`, `move_exceeded_2pct_5d`, `quality_signal`

---

#### 1.2 Volume Baselines — 20d Average Volume Per Contract

**Why second:** The definition of "unusual" is `volume / avg_volume_20d ≥ 3.0`.
Without baselines, you cannot classify any event as unusual. This must exist before
unusual volume detection can run.

**How:** Derived from options chain history (not a direct API call). Pull the last
30 trading days of EOD chain snapshots → compute per-contract rolling average.
This is the **bootstrapping step** for `options_volume_baseline` in Postgres.

**Estimate:** ~30 days × 12 symbols × ~2,000 contracts per symbol =
~720,000 rows in `options_chain_snapshots`. Schwab API allows historical chain
pulls day-by-day. At 1 call per symbol per day: 12 × 30 = 360 calls. ~15 min.

---

#### 1.3 Historical Options Chain Snapshots — EOD Only, 90 Days Back

**Why third:** The chain snapshots ARE the raw training data. Every unusual volume
event is detected by comparing a snapshot to the baseline. The more history, the
more labeled training events you have. At ~50 events/day across the watchlist,
90 days = ~4,500 potential signal_catalog rows to train on.

**What to pull:** End-of-day snapshots for the last 90 trading days, all 12 tickers.
Schwab `/marketdata/v1/chains` accepts `fromDate`/`toDate` params; pull one snapshot
per ticker per trading day at 15:55 ET (last 5 minutes, highest volume).

**Notes:**
- Pull ALL strikes (range=ALL), ALL expiries up to 90 DTE
- Schwab historical chain availability: typically 2-5 years back for liquid names
- Rate limit: ~120 requests/min on free tier; 360 calls = 3 minutes at safe pace

---

### TIER 2 — Signal Quality (improves model features significantly)

#### 2.1 Unusual Volume Event Detection — Historical Scan

**Why:** Once Tier 1 is done, scan all historical chain snapshots against the baselines
to populate `options_unusual_volume_events` and `signal_catalog`. This generates the
actual rows the ML models train on. Run this as a pure computation pass — no API calls.

**Expected yield:** ~4,500 chain snapshots → typically 10-50 unusual events per day
per watchlist = **1,000–3,000 initial labeled training rows**. Enough to get first
models off the ground.

**Labeling:** Join each event row with underlying price history (from 1.1) to compute
all follow-through columns. Any event where T+5 price is available gets a label.

---

#### 2.2 IV Surface Snapshots — Historical Hourly

**Why:** `iv_rank`, `iv_percentile`, `skew_25d`, `term_slope` are some of the most
predictive features. Without them, the models have no volatility regime context.

**What to pull:** Hourly IV surface data going back 60 days. For each ticker,
pull ATM IV, 25-delta skew, and 30/60/90d implied vols.

**Compute:**
- `iv_rank` = (current_iv - iv_52w_low) / (iv_52w_high - iv_52w_low) × 100
- `skew_25d` = (25d put IV - 25d call IV) normalized
- `term_slope` = (60d ATM IV - 30d ATM IV) / 30

**Storage:** `iv_surface_snapshots` in TOS QuestDB.

---

#### 2.3 Earnings Calendar

**Why:** `days_to_earnings` and `is_within_2w_earnings` are important for distinguishing
informed flow from earnings speculation. Events 2-4 weeks before earnings that are
directionally correct in 60%+ of cases are worth paying more attention to.

**Source:** Schwab API has earnings calendar per symbol. Also supplement with yfinance
(already available in MarketAI).

**Update frequency:** Nightly, or whenever a new earnings date is announced.

---

### TIER 3 — Live Operations (ongoing once the pipeline is running)

#### 3.1 Intraday Chain Snapshots — Every 5 Minutes, Market Hours

The core ongoing collection. Every 5 minutes during 9:30–16:00 ET:
- Pull full chain for all 12 tickers
- Run unusual volume detection vs baseline
- Write events to `options_unusual_volume_events`
- Write new signal_catalog rows (unlabeled)

**Rate budget:** 12 symbols × 78 snapshots/day = 936 calls/day. Comfortably within
Schwab API limits.

#### 3.2 EOD Follow-Through Labels — 4:30 PM ET Daily

After market close each day:
- For all signal_catalog rows from 1 day ago: compute `underlying_return_1d_fwd`
- For all signal_catalog rows from 5 days ago: compute `underlying_return_5d_fwd`,
  `direction_correct_5d`, `quality_signal`
- Update `options_volume_baseline` with today's chain data (rolling 20d avg)

This is the most important EOD job — without it, signals never get labeled and the
model cannot improve.

#### 3.3 Baseline Refresh — Weekly

Rolling 20d volume averages drift. Refresh baselines every Sunday evening using the
past 20 trading days of chain data. Critical for keeping unusual volume thresholds
calibrated.

---

## Collection Schedule

```
┌────────────────────────────────────────────────────────────────┐
│ ONE-TIME BACKFILL (runs once on API key activation)            │
├─────────────────────────────┬──────────────┬───────────────────┤
│ Flow                        │ Duration     │ Produces          │
├─────────────────────────────┼──────────────┼───────────────────┤
│ 1. underlying_price_backfill│ ~20 min      │ 2yr OHLCV + 1h    │
│ 2. chain_backfill (90d EOD) │ ~45 min      │ 90d chain history │
│ 3. baseline_compute         │ ~5 min       │ vol_baseline table│
│ 4. historical_uv_detection  │ ~10 min      │ signal_catalog    │
│ 5. historical_label_fill    │ ~5 min       │ labeled signals   │
│ 6. iv_surface_backfill (60d)│ ~30 min      │ iv_surface table  │
│ 7. earnings_calendar_init   │ ~2 min       │ earnings_calendar │
├─────────────────────────────┴──────────────┴───────────────────┤
│ TOTAL: ~2 hours wall-clock. Runs sequentially (each depends    │
│ on previous output). On day 1 you have training data.          │
└────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────┐
│ INTRADAY SCHEDULE (market days only)                           │
├──────────────┬────────────────┬───────────────────────────────┤
│ Time (ET)    │ Flow           │ Action                        │
├──────────────┼────────────────┼───────────────────────────────┤
│ 09:25        │ market_open    │ warm up connections, pre-check│
│ 09:30–16:00  │ chain_snapshot │ every 5 min, 12 tickers       │
│ 09:30–16:00  │ uv_detection   │ runs after every snapshot     │
│ Hourly       │ iv_surface     │ ATM IV + skew + term struct   │
│ 16:00        │ market_close   │ final snapshot, flag EOD      │
│ 16:30        │ eod_labels     │ T+1 label fill, baseline upd  │
│ 22:00        │ nightly_retrain│ MarketAI retrains if new data │
│              │ (MarketAI)     │ (existing flow, triggered here)│
└──────────────┴────────────────┴───────────────────────────────┘

┌────────────────────────────────────────────────────────────────┐
│ WEEKLY SCHEDULE                                                │
├──────────────┬────────────────────────────────────────────────┤
│ Sunday 20:00 │ baseline_refresh — recompute rolling 20d avgs  │
│ Sunday 20:30 │ earnings_calendar_refresh — next 4 weeks        │
│ Sunday 21:00 │ granger_causality_research (MarketAI)          │
└──────────────┴────────────────────────────────────────────────┘
```

---

## Prefect Flow Architecture

```
                    ┌─────────────────┐
                    │  Prefect Server  │
                    │  (port 4200)     │
                    │  shared with     │
                    │  MarketAI        │
                    └────────┬────────┘
                             │ orchestrates
              ┌──────────────┼──────────────────┐
              │              │                  │
              ▼              ▼                  ▼
    ┌──────────────┐ ┌──────────────┐  ┌──────────────┐
    │  TOS         │ │  TOS         │  │  MarketAI    │
    │  Backfill    │ │  Intraday    │  │  ML Flows    │
    │  Flows       │ │  Flows       │  │  (existing)  │
    └──────┬───────┘ └──────┬───────┘  └──────┬───────┘
           │                │                  │
           ▼                ▼                  │
    ┌────────────────────────────┐             │
    │  tos-questdb  tos-postgres │ ◄───────────┘
    │  (port 9100)  (port 5433)  │   reads for ML
    └────────────────────────────┘
```

### Flow dependency chain:

```
underlying_price_backfill
        │
        ▼
chain_backfill (90d)
        │
        ▼
baseline_compute ───────────────────────────┐
        │                                   │
        ▼                                   ▼
historical_uv_detection          intraday_chain_snapshot (live)
        │                                   │
        ▼                                   ▼
historical_label_fill            intraday_uv_detection (live)
        │                                   │
        └──────────────┬────────────────────┘
                       ▼
               eod_label_update (daily 4:30 PM)
                       │
                       ▼
              MarketAI nightly_retrain (22:00 PM)
                       │
                       ▼
              MarketAI signal_scoring (every 15 min)
```

---

## Schwab API Rate Limits and Throttling

| Plan       | Requests/min | Requests/day | Notes |
|------------|-------------|-------------|-------|
| Individual | 120         | ~120,000    | Standard OAuth2 app |
| Bulk       | 600+        | Unlimited   | Enterprise/broker |

**Strategy:** Use a token bucket throttler. Set `_RATE_LIMIT = 100/min` (20% headroom).
For backfill, add `asyncio.sleep(0.6)` between calls. For intraday, 12 calls/5min =
2.4 calls/min — far below limit.

**Retry policy:** 429 Too Many Requests → exponential backoff starting at 5s.
503/504 → retry up to 3x with 10s delay.

---

## What You'll Have After Day 1 (API key live)

| Dataset | Rows | Ready for |
|---------|------|-----------|
| underlying OHLCV | ~6,000 daily bars + hourly | Label computation, RSI features |
| options chains | ~90 EOD snapshots × 12 symbols | Baseline, signal detection |
| volume baselines | ~24,000 contract rows | Unusual volume threshold |
| signal_catalog | 1,000–3,000 labeled events | **First model training run** |
| iv_surface | ~1,440 hourly snapshots | Regime features |
| earnings_calendar | ~60 future events | Earnings proximity feature |

**First training run: day 2.** SignalQualityModel and DirectionModels can train with
as few as 300 labeled rows. The walk-forward CV needs at least 3 months of data for
full confidence; 90 days of history provides exactly that baseline.

---

## File Structure

```
tos-collector/
├── collectors/
│   ├── schwab_client.py       # OAuth2 + rate-limited API client
│   ├── chain_collector.py     # options chain pulls + parsing
│   └── price_collector.py     # underlying OHLCV pulls
├── detectors/
│   ├── unusual_volume.py      # threshold detection logic
│   └── label_computer.py      # follow-through return computation
├── db/
│   ├── questdb_writer.py      # ILP writer for QuestDB
│   └── postgres_writer.py     # psycopg2 writer for signal_catalog
├── flows/
│   ├── historical_backfill.py # one-time backfill flow
│   ├── intraday_collection.py # live 5-min chain + UV detection
│   ├── eod_processing.py      # label fill + baseline refresh
│   └── deploy.py              # Prefect deployment registration
├── docker-compose.yml          # tos-questdb + tos-postgres + collector
└── requirements.txt
```
