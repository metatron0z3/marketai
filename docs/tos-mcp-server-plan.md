# ThinkorSwim MCP Server — Ingest Plan

**Purpose:** A standalone MCP server that owns all TOS/Schwab data acquisition. MarketAI
connects to its databases to run ML pipelines. This server has no ML responsibilities —
it collects, normalizes, and exposes raw market data.

**Focus:** Unusual options volume detection and the full data context needed to evaluate it.

---

## Architecture

```
┌─────────────────────────────────────────┐
│         ThinkorSwim MCP Server          │
│                                         │
│  Schwab API ──► Collectors ──► QuestDB  │
│  TOS Scanner ──► Normalizer ──► Postgres│
│                                         │
│  MCP Tools (exposed to MarketAI/Claude) │
└─────────────────────────────────────────┘
           │                │
           ▼                ▼
       QuestDB           Postgres
    (time-series)     (reference/signals)
           │                │
           └────────────────┘
                    │
                    ▼
              MarketAI reads
              for ML pipeline
```

**Databases:**
- **QuestDB** (port 9100, separate from MarketAI's 9000) — all time-series tick data
- **PostgreSQL** (port 5433, separate from any MarketAI postgres) — reference tables,
  watchlist, signal catalog, baseline volume, model registry

---

## Symbol Universe & Per-Ticker Instructions

### Current Holdings (data already collected in MarketAI)

| Symbol | Type | Data Already In MarketAI | Priority |
|--------|------|--------------------------|----------|
| TSLA | Equity | Databento tick data; yfinance daily OHLCV; Massive API calls Q1+Q2 2025, Q1 2026 ✅; Q3+Q4 2025 calls ❌ failed | **High** |
| NVDA | Equity | yfinance daily OHLCV; Massive API calls Q1+Q2+Q1-26 ✅, Q3 2025 🔄 in progress | **High** |
| SPY | ETF | Databento tick data (options_trades); yfinance daily OHLCV | **High** |
| QQQ | ETF | Databento tick data (options_trades); yfinance daily OHLCV | **High** |
| AAPL | Equity | yfinance daily OHLCV only — no options data collected yet | **High** |
| AMD | Equity | yfinance daily OHLCV only — no options data collected yet | **Medium** |
| META | Equity | yfinance daily OHLCV only — no options data collected yet | **Medium** |
| AMZN | Equity | Registered in yfinance map, likely no bars fetched yet | **Medium** |
| MSFT | Equity | Registered in yfinance map, likely no bars fetched yet | **Medium** |
| GLD | ETF | Registered in yfinance map, likely no bars fetched yet | **Low** |
| TLT | ETF | Registered in yfinance map, likely no bars fetched yet | **Low** |
| SPX | Index | Registered in yfinance map (daily close only) | **Medium** |

---

### Per-Ticker Collection Instructions

---

#### TSLA — Tesla Inc.
**Why it matters:** Highest retail options volume of any single stock. Enormous sweep
activity around Elon news, earnings, and macro moves. The existing Massive API options bars
make this the primary ticker for initial ML training.

**What we already have:** Options bars (calls, 2025 Q1+Q2+Q1-26); yfinance daily OHLCV;
Databento tick-level options trades.

**What TOS should collect:**
- **Chain snapshots:** every 5 minutes, 9:30am–4:00pm ET, full chain (ALL strikes, ALL expiries)
- **Unusual volume detection:** run on every snapshot. Threshold: volume_ratio_20d ≥ 3.0, min 500 contracts, min $50k premium
- **Sweep detection:** TSLA sweeps are very common and highly informative. Flag any single contract gaining >1000 contracts between two 5-min snapshots at or above ask
- **0DTE tracking:** TSLA has extremely active 0-day options (Friday expirations especially). Add a separate scan for contracts expiring same day with volume > 200
- **IV surface:** hourly snapshots. TSLA IV rank swings dramatically — capture term structure and skew
- **Intraday bars:** 1m and 5m resolution during market hours
- **Historical backfill target:** 2024-01-01 → present, daily chain EOD snapshots

**Special notes:**
- TSLA options are often driven by retail meme momentum, not pure informed flow. The
  regime model needs to learn to discount TSLA unusual volume during high-VIX, down-market
  days (correlation with market drops) vs. idiosyncratic TSLA events.
- Earnings (quarterly): IV typically spikes 2 weeks before and crushes the day after.
  Flag all signals within 14 days of earnings with `days_to_earnings` feature.
- The puts side (not yet collected in Massive) should be added here from day one.
  Both calls and puts have strong signal characteristics for TSLA.

---

#### NVDA — NVIDIA Corporation
**Why it matters:** The defining AI-era stock. Institutional options flow is enormous and
often precedes multi-day moves of 5-15%. High open interest in calls reflects persistent
bullish positioning. The Massive API data already collected makes this the second primary
ML training ticker.

**What we already have:** Options bars (calls, Q1+Q2 2025 + Q1 2026 ✅, Q3 2025 🔄);
yfinance daily OHLCV.

**What TOS should collect:**
- **Chain snapshots:** every 5 minutes, full chain
- **Unusual volume detection:** threshold same as TSLA. Pay special attention to
  far-OTM calls (>20% OTM) — NVDA has had repeated instances of deep OTM call buying
  that preceded large moves
- **IV surface:** every 30 minutes (NVDA IV rank is one of the most informative features
  in the project — it ranges from <20 in calm periods to >80 around earnings)
- **Block trade detection:** NVDA sees large institutional block trades (>5000 contracts
  in a single print). Flag any single contract with volume >2000 between snapshots
- **Intraday bars:** 1m and 5m
- **Historical backfill target:** 2024-01-01 → present

**Special notes:**
- NVDA earnings have been among the most option-significant events in the market.
  Collect the full chain snapshot at 3:45pm on earnings day (before report) and
  again at 9:35am the following morning.
- The puts side needs to be collected. Unusual put buying in NVDA has been a reliable
  leading indicator of short-term corrections.
- Sector correlation: when NVDA unusual volume co-occurs with AMD, SMCI, or AVGO
  unusual volume, it is a much stronger signal. Track this cross-ticker cluster pattern.

---

#### SPY — SPDR S&P 500 ETF
**Why it matters:** Dual role: (1) a direct trading signal (unusual SPY put volume often
precedes market selloffs) and (2) the primary market regime indicator. SPY options are
the most liquid in the world — signals here reflect true institutional intent.

**What we already have:** Databento tick-level options trades; yfinance daily OHLCV.

**What TOS should collect:**
- **Chain snapshots:** every 5 minutes, full chain. Focus on near-term expiries (0-30 DTE)
  which drive the largest unusual volume events
- **0DTE tracking:** SPY 0DTE options are the most traded contracts in existence. Add a
  dedicated scan: every 5 minutes, 0DTE contracts only, flag any gaining >5000 contracts
  per snapshot
- **Large block detection:** threshold $500k+ premium for SPY (institutional scale).
  Flag any single contract event with total premium > $500k
- **IV surface:** every 30 minutes. SPY term structure (VIX vs VIX3M) is a key regime
  indicator. Capture the 5 nearest expiries' ATM IVs to reconstruct term structure
- **Put/call ratio:** compute and store in `ticker_daily_summary` with hourly granularity
  (not just EOD) — the intraday P/C ratio shift is a useful feature
- **Intraday bars:** 1m resolution (used for momentum features across all tickers)
- **Historical backfill target:** 2023-01-01 → present (SPY has the richest history
  and every ML model uses it for regime features)

**Special notes:**
- SPY unusual volume often leads sector ETF and single-stock moves by 30-60 minutes.
  Build a cross-ticker lag feature: `spy_unusual_vol_30min_ago`.
- Large SPY put blocks are a professional hedging signal, not necessarily a directional
  bet. Flag put premiums > $1M as "institutional hedge" vs. smaller speculative prints.
- The existing Databento tick data for SPY covers options_trades — reconcile with TOS
  chain snapshots to validate baseline volume numbers.

---

#### QQQ — Invesco QQQ ETF (Nasdaq-100)
**Why it matters:** Tech sector proxy. Highly correlated with NVDA, AAPL, MSFT, META.
Unusual QQQ volume often anticipates moves in the entire tech sector before individual
stocks react.

**What we already have:** Databento tick-level options trades; yfinance daily OHLCV.

**What TOS should collect:**
- **Chain snapshots:** every 5 minutes, full chain, near-term focus (0-45 DTE)
- **Unusual volume detection:** same thresholds. Look especially for large call sweeps —
  these often precede 2-3% rallies in the Nasdaq within 2-5 days
- **Cross-ticker cluster flag:** when QQQ unusual volume co-occurs with NVDA and/or AAPL
  unusual volume within the same trading hour, composite conviction is significantly higher
- **IV surface:** hourly
- **Intraday bars:** 1m and 5m
- **Historical backfill target:** 2023-01-01 → present

---

#### AAPL — Apple Inc.
**Why it matters:** Most liquid single-stock options globally. Extremely high open interest.
Institutional options activity in AAPL often reflects broader market positioning
(AAPL is ~7% of SPY and QQQ). Very large block trades are common.

**What we already have:** yfinance daily OHLCV only. No options data collected.

**What TOS should collect:**
- **Chain snapshots:** every 5 minutes, full chain
- **Block trade focus:** AAPL's unusual volume tends to be large blocks ($1M+ premium)
  rather than sweeps. Tune detection: min premium $100k for AAPL (higher bar than TSLA)
- **Unusual volume detection:** standard thresholds, but note AAPL baseline volume is very
  high — a 3x ratio event in AAPL represents massive notional premium
- **IV surface:** hourly. AAPL IV rank is typically low (25-40) except around earnings
- **Intraday bars:** 1m and 5m
- **Historical backfill target:** 2024-01-01 → present

**Special notes:**
- AAPL earnings (January, April, July, October) are high-signal events for unusual volume.
  Begin tracking unusual volume 3 weeks before earnings.
- iPhone launch cycles (September) also drive notable options activity.

---

#### AMD — Advanced Micro Devices
**Why it matters:** High-beta semiconductor that often moves in sympathy with NVDA but
has its own narrative (datacenter GPUs, AI accelerators). Very active retail + institutional
options flow. Options are liquid enough for reliable signal detection.

**What we already have:** yfinance daily OHLCV only. No options data collected.

**What TOS should collect:**
- **Chain snapshots:** every 5 minutes, full chain
- **Unusual volume detection:** standard thresholds. AMD has frequent 5-10x volume ratio
  events before moves — the signal is often cleaner than NVDA because AMD has fewer
  passive index inflows distorting the baseline
- **NVDA correlation flag:** when AMD and NVDA see unusual volume in the same direction
  within the same session, flag this as a `sector_cluster` event
- **Intraday bars:** 5m and 15m (1m is less critical for AMD)
- **Historical backfill target:** 2024-01-01 → present

---

#### META — Meta Platforms
**Why it matters:** Large earnings moves (5-15% post-earnings is common). Very active
institutional call buying. AI narrative (Llama, Reels, Reality Labs) drives episodic
unusual volume spikes.

**What we already have:** yfinance daily OHLCV only. No options data collected.

**What TOS should collect:**
- **Chain snapshots:** every 5 minutes, full chain
- **Earnings focus:** META has some of the highest IV pre-earnings of any mega-cap.
  Ramp up snapshot frequency to every 2 minutes in the 48 hours before earnings
- **Unusual volume detection:** standard thresholds. Flag call sweeps with DTE < 30
  that occur > 2 weeks before earnings (early positioning signal)
- **IV surface:** hourly, with special attention to skew (META tends to have elevated
  put skew around regulatory/privacy news cycles)
- **Intraday bars:** 5m and 15m
- **Historical backfill target:** 2024-01-01 → present

---

#### AMZN — Amazon.com
**Why it matters:** AWS and e-commerce dual narrative. Very liquid options. Large earnings
moves (5-12%). Lower volatility than TSLA/NVDA so unusual volume events are rarer but
more meaningful when they occur.

**What we already have:** Registered in yfinance map; no bars or options likely collected.

**What TOS should collect:**
- **Chain snapshots:** every 10 minutes (medium priority relative to TSLA/NVDA/AAPL)
- **Unusual volume detection:** raise the minimum premium threshold to $150k for AMZN
  (higher stock price means each contract costs more, so fewer events but higher quality)
- **Intraday bars:** 15m resolution is sufficient for AMZN
- **Historical backfill target:** 2024-06-01 → present

---

#### MSFT — Microsoft Corporation
**Why it matters:** Azure AI growth and Copilot narrative. Options activity is calmer than
NVDA but more institutional. A good "quality signal" benchmark — MSFT unusual volume
tends to be cleaner (less retail noise) than smaller-cap names.

**What we already have:** Registered in yfinance map; no bars likely collected.

**What TOS should collect:**
- **Chain snapshots:** every 10 minutes
- **Unusual volume detection:** standard thresholds, but expect lower frequency — treat
  each event as higher baseline quality than TSLA/AMD
- **Intraday bars:** 15m resolution
- **Historical backfill target:** 2024-06-01 → present

---

#### GLD — SPDR Gold ETF
**Why it matters:** Not a primary options signal target. Used as a **macro regime
indicator**: unusual put volume in GLD signals gold selling (risk-on, equities likely
rallying); unusual call volume signals flight to safety (risk-off, equities may sell).

**What we already have:** Registered in yfinance map; likely no bars fetched.

**What TOS should collect:**
- **Chain snapshots:** every 30 minutes (low frequency — GLD options move slowly)
- **Unusual volume detection:** run daily EOD only (not intraday). Track the direction
  (calls vs puts) and add as a feature `gld_flow_direction` for the regime model
- **Intraday bars:** daily bars only
- **No sweep detection needed** — GLD sweeps are rare and not informative for equity signals

---

#### TLT — iShares 20+ Year Treasury ETF
**Why it matters:** Bond market proxy. TLT unusual put volume signals expectation of rising
rates (bearish for growth stocks, especially tech). TLT unusual call volume signals rate
cuts expected (bullish for NVDA, META, TSLA). Extremely useful cross-asset regime feature.

**What we already have:** Registered in yfinance map; likely no bars fetched.

**What TOS should collect:**
- **Chain snapshots:** every 30 minutes
- **Unusual volume detection:** daily EOD. Store `tlt_flow_direction` and `tlt_premium_total`
  as regime features consumed by MarketAI's models
- **IV surface:** daily snapshot — TLT's term structure reflects the rates vol market
- **Intraday bars:** daily bars only
- **No sweep detection needed**

---

#### SPX — S&P 500 Index (use SPXW on TOS for weeklies)
**Why it matters:** SPX options are European-style, cash-settled, and exclusively
institutional. No retail noise. A $1M+ SPX put block is genuine macro hedging by a
fund. These are the clearest "smart money" signals in the options market.

**What we already have:** Registered in yfinance map (daily close only).

**What TOS should collect:**
- **Chain snapshots:** every 5 minutes for SPXW (weekly expirations), every 30 minutes
  for monthly SPX expirations
- **Large block focus:** set minimum premium at $500k for SPX (institutional-only scale).
  Ignore anything below — small SPX prints are not meaningful
- **Put wall tracking:** track which SPX strikes have the highest OI (these become
  gamma pin levels and support/resistance). Store weekly in postgres as `spx_put_wall`
- **IV surface:** every 30 minutes. SPX term structure (1w vs 1m vs 3m ATM IV) is the
  most reliable forward-looking vol indicator in the market
- **Intraday bars:** no equity bars (SPX is not tradable directly); use SPY 1m bars as proxy

**Special notes:**
- TOS ticker for weekly SPX options is `SPXW`. Monthly is `SPX`. Collect both.
- Large SPX put buying (>$5M premium in a single block) should trigger an immediate
  alert and be stored as a `macro_hedge_event` in a separate postgres table.

---

### Recommended Additions (not yet in MarketAI, high value for unusual volume)

These tickers have very high unusual options volume activity and would strengthen the
ML training dataset significantly. Add to the watchlist once core collection is stable:

| Symbol | Rationale | Priority |
|--------|-----------|----------|
| PLTR | AI/defense narrative; very high retail + institutional overlap; large sweeps common | High |
| MSTR | Bitcoin proxy; extreme gamma events; useful as crypto-sentiment indicator | High |
| COIN | Crypto native; correlated with BTC options market; high unusual volume frequency | Medium |
| SMCI | AI server hardware; extreme volatility; frequent multi-strike cluster events | Medium |
| ARM | Semiconductor IP; AI narrative; IPO recency means less noisy baseline | Medium |
| GOOGL | AI narrative (Gemini); very liquid options; institutional block trades common | Medium |
| XLK | Tech sector ETF; unusual volume here leads single-stock tech moves | Medium |
| AVGO | Broadcom; AI networking; high institutional options activity | Low |

---

## QuestDB Schemas (Time-Series)

### 1. `options_chain_snapshots`
Full options chain per symbol, snapshotted every 5 minutes during market hours.
This is the foundational table — everything is derived from it.

```sql
CREATE TABLE options_chain_snapshots (
    snapshot_ts         TIMESTAMP,
    underlying_symbol   SYMBOL,
    expiry              DATE,
    days_to_expiry      INT,
    strike              DOUBLE,
    option_type         SYMBOL,       -- 'C' or 'P'
    bid                 DOUBLE,
    ask                 DOUBLE,
    last                DOUBLE,
    mark                DOUBLE,       -- (bid+ask)/2
    volume              LONG,
    open_interest       LONG,
    delta               DOUBLE,
    gamma               DOUBLE,
    theta               DOUBLE,
    vega                DOUBLE,
    rho                 DOUBLE,
    implied_vol         DOUBLE,
    iv_rank             DOUBLE,       -- 0-100, TOS-provided
    iv_percentile       DOUBLE,       -- 0-100, TOS-provided
    underlying_price    DOUBLE,
    in_the_money        BOOLEAN,
    theo_price          DOUBLE,
    intrinsic_value     DOUBLE,
    extrinsic_value     DOUBLE,
    bid_size            LONG,
    ask_size            LONG,
    last_trade_size     LONG,
    open_price          DOUBLE,       -- option open for the day
    high_price          DOUBLE,
    low_price           DOUBLE,
    net_change          DOUBLE,       -- vs prior close
    volatility_change   DOUBLE,       -- IV change vs prior snapshot
    multiplier          INT           -- usually 100
) TIMESTAMP(snapshot_ts) PARTITION BY DAY;
```

**Collection:** Schwab `GET /marketdata/v1/chains` with `includeQuotes=TRUE`,
`range=ALL`, `optionType=ALL`. Run for every symbol in watchlist every 5 minutes,
9:30am–4:00pm ET.

---

### 2. `options_unusual_volume_events`
Detected unusual volume events — the primary signal table.
Written whenever a chain snapshot reveals a contract exceeding thresholds.

```sql
CREATE TABLE options_unusual_volume_events (
    detected_ts             TIMESTAMP,
    underlying_symbol       SYMBOL,
    expiry                  DATE,
    days_to_expiry          INT,
    strike                  DOUBLE,
    option_type             SYMBOL,
    moneyness               SYMBOL,   -- 'OTM', 'ATM', 'ITM'
    otm_pct                 DOUBLE,   -- positive=OTM, negative=ITM
    volume                  LONG,
    prior_snapshot_volume   LONG,     -- volume at last snapshot
    volume_delta            LONG,     -- volume gained since last snapshot
    avg_volume_10d          DOUBLE,
    avg_volume_20d          DOUBLE,
    volume_ratio_10d        DOUBLE,   -- volume / avg_volume_10d
    volume_ratio_20d        DOUBLE,
    open_interest           LONG,
    vol_oi_ratio            DOUBLE,   -- volume / open_interest
    bid                     DOUBLE,
    ask                     DOUBLE,
    mark                    DOUBLE,
    ba_spread_pct           DOUBLE,   -- (ask-bid)/mark
    implied_vol             DOUBLE,
    iv_rank                 DOUBLE,
    iv_percentile           DOUBLE,
    delta                   DOUBLE,
    gamma                   DOUBLE,
    theta                   DOUBLE,
    vega                    DOUBLE,
    underlying_price        DOUBLE,
    underlying_return_1d    DOUBLE,   -- stock return today so far
    premium_total           DOUBLE,   -- mark * volume * 100
    notional_value          DOUBLE,   -- underlying_price * delta * volume * 100
    detection_method        SYMBOL,   -- 'chain_diff', 'tos_scanner', 'threshold'
    scanner_rank            INT,      -- position in TOS unusual activity list
    session                 SYMBOL    -- 'PREMARKET', 'REGULAR', 'AFTERHOURS'
) TIMESTAMP(detected_ts) PARTITION BY DAY;
```

**Detection logic (Python, runs after each chain snapshot):**
```python
VOLUME_RATIO_THRESHOLD = 3.0   # volume > 3x 20d avg
MIN_ABSOLUTE_VOLUME    = 500   # at least 500 contracts
MIN_PREMIUM            = 50_000  # at least $50k notional
MAX_DTE                = 90
MIN_DTE                = 1

def detect_unusual(snapshot_row, baseline):
    ratio = snapshot_row.volume / baseline.avg_volume_20d
    premium = snapshot_row.mark * snapshot_row.volume * 100
    return (
        ratio >= VOLUME_RATIO_THRESHOLD
        and snapshot_row.volume >= MIN_ABSOLUTE_VOLUME
        and premium >= MIN_PREMIUM
        and MIN_DTE <= snapshot_row.days_to_expiry <= MAX_DTE
    )
```

---

### 3. `options_sweep_events`
Sweep trades: same contract, multiple exchanges, executed within a short time window.
Indicates urgency — someone wants to be filled NOW regardless of price.

```sql
CREATE TABLE options_sweep_events (
    event_ts            TIMESTAMP,
    underlying_symbol   SYMBOL,
    expiry              DATE,
    days_to_expiry      INT,
    strike              DOUBLE,
    option_type         SYMBOL,
    total_size          LONG,
    avg_fill_price      DOUBLE,
    premium             DOUBLE,       -- avg_fill_price * total_size * 100
    exchange_count      INT,          -- how many exchanges hit
    exchanges           STRING,       -- comma-separated exchange codes
    time_window_ms      INT,          -- how fast it was filled
    side                SYMBOL,       -- 'BUY', 'SELL', 'UNKNOWN'
    implied_vol         DOUBLE,
    delta               DOUBLE,
    underlying_price    DOUBLE,
    above_ask           BOOLEAN,      -- aggressor paid above ask
    below_bid           BOOLEAN       -- aggressor sold below bid
) TIMESTAMP(event_ts) PARTITION BY DAY;
```

**Note:** Schwab's streaming Level 1 options feed does not give exchange-by-exchange
fills. Capture sweeps via: (a) volume jumping > 500 contracts between 5-minute snapshots
in the same contract, above ask price, OR (b) TOS-flagged sweeps from the scanner.

---

### 4. `underlying_intraday_bars`
OHLCV bars for underlying stocks at multiple resolutions.
Used for momentum, technical context, and labeling.

```sql
CREATE TABLE underlying_intraday_bars (
    bar_ts      TIMESTAMP,
    symbol      SYMBOL,
    resolution  SYMBOL,   -- '1m', '5m', '15m', '30m', '1h', '1d'
    open        DOUBLE,
    high        DOUBLE,
    low         DOUBLE,
    close       DOUBLE,
    volume      LONG,
    vwap        DOUBLE,
    source      SYMBOL    -- 'schwab', 'tos'
) TIMESTAMP(bar_ts) PARTITION BY DAY;
```

**Collection:** Schwab `GET /marketdata/v1/pricehistory`. Run for all watchlist symbols.
- 1m bars: during market hours, every 1 minute (or pull last 30 days once daily)
- 5m/15m bars: pull weekly
- 1d bars: pull nightly for last 2 years (for momentum features)

---

### 5. `iv_surface_snapshots`
Options IV term structure and skew per symbol, once per hour.
Captures how the vol surface evolves — critical for regime features.

```sql
CREATE TABLE iv_surface_snapshots (
    snapshot_ts     TIMESTAMP,
    symbol          SYMBOL,
    expiry          DATE,
    days_to_expiry  INT,
    atm_iv          DOUBLE,       -- ATM straddle IV
    call_25d_iv     DOUBLE,       -- 25-delta call IV
    put_25d_iv      DOUBLE,       -- 25-delta put IV
    skew_25d        DOUBLE,       -- put_25d - call_25d (+ = put skew)
    call_10d_iv     DOUBLE,
    put_10d_iv      DOUBLE,
    iv_rank         DOUBLE,
    iv_percentile   DOUBLE,
    hv_10d          DOUBLE,       -- 10-day historical vol (from price bars)
    hv_20d          DOUBLE,       -- 20-day historical vol
    hv_30d          DOUBLE,
    iv_hv_ratio     DOUBLE,       -- atm_iv / hv_20d (IV premium/discount)
    term_slope      DOUBLE        -- (far_expiry_atm_iv - near_expiry_atm_iv)
) TIMESTAMP(snapshot_ts) PARTITION BY DAY;
```

---

### 6. `ticker_daily_summary`
End-of-day aggregated options metrics per ticker.
Used for daily feature computation and follow-through labeling.

```sql
CREATE TABLE ticker_daily_summary (
    trade_date              TIMESTAMP,
    symbol                  SYMBOL,
    total_call_volume       LONG,
    total_put_volume        LONG,
    put_call_volume_ratio   DOUBLE,
    total_call_oi           LONG,
    total_put_oi            LONG,
    put_call_oi_ratio       DOUBLE,
    unusual_call_events     INT,      -- count of events for this day
    unusual_put_events      INT,
    total_call_premium      DOUBLE,   -- total unusual call premium
    total_put_premium       DOUBLE,
    max_single_premium      DOUBLE,   -- largest single unusual event premium
    dominant_expiry         DATE,     -- expiry with most unusual volume
    dominant_strike         DOUBLE,
    atm_iv                  DOUBLE,
    iv_rank                 DOUBLE,
    iv_change_1d            DOUBLE,   -- IV rank change from prior day
    underlying_open         DOUBLE,
    underlying_close        DOUBLE,
    underlying_return_1d    DOUBLE,
    underlying_volume       LONG,
    underlying_vol_ratio    DOUBLE    -- vs 20d avg volume
) TIMESTAMP(trade_date) PARTITION BY MONTH;
```

---

## PostgreSQL Schemas (Reference / Relational)

### `watchlist`
```sql
CREATE TABLE watchlist (
    id              SERIAL PRIMARY KEY,
    symbol          VARCHAR(20) NOT NULL UNIQUE,
    active          BOOLEAN DEFAULT TRUE,
    priority        INT DEFAULT 2,        -- 1=high, 2=medium, 3=low
    sector          VARCHAR(50),
    market_cap_tier VARCHAR(10),          -- 'mega', 'large', 'mid', 'small'
    earnings_date   DATE,
    notes           TEXT,
    added_at        TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Suggested seed list for unusual options volume hunting:
-- Large-cap, liquid options, high retail + institutional interest
-- AAPL, NVDA, TSLA, META, AMZN, MSFT, GOOGL, AMD, SPY, QQQ, IWM
-- High-beta: PLTR, MSTR, COIN, HOOD, SOFI, GME
-- Biotech event-driven: LLY, MRNA, BIIB
```

### `options_volume_baseline`
Historical average volume per contract, recomputed nightly.
Used to calculate volume_ratio at detection time.

```sql
CREATE TABLE options_volume_baseline (
    symbol              VARCHAR(20),
    expiry              DATE,
    strike              DOUBLE PRECISION,
    option_type         CHAR(1),
    avg_volume_5d       DOUBLE PRECISION,
    avg_volume_10d      DOUBLE PRECISION,
    avg_volume_20d      DOUBLE PRECISION,
    avg_volume_30d      DOUBLE PRECISION,
    avg_oi_20d          DOUBLE PRECISION,
    pct_75_volume       DOUBLE PRECISION,   -- 75th percentile daily volume
    pct_90_volume       DOUBLE PRECISION,
    pct_95_volume       DOUBLE PRECISION,
    trading_days_count  INT,                -- how many days of data
    computed_at         TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (symbol, expiry, strike, option_type)
);
```

**Refresh job (nightly, post-market):**
```python
# Pull last 30 days of end-of-day chain snapshots from QuestDB
# Compute rolling averages and percentiles per contract
# Upsert into options_volume_baseline
# This ensures volume_ratio is always computed against a fresh baseline
```

### `signal_catalog`
Every detected unusual volume event with follow-through tracking.
This is the training data source for MarketAI's ML pipeline.

```sql
CREATE TABLE signal_catalog (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    detected_at             TIMESTAMPTZ NOT NULL,
    symbol                  VARCHAR(20) NOT NULL,
    expiry                  DATE,
    days_to_expiry          INT,
    strike                  DOUBLE PRECISION,
    option_type             CHAR(1),
    moneyness               VARCHAR(5),
    otm_pct                 DOUBLE PRECISION,
    volume                  BIGINT,
    volume_ratio_20d        DOUBLE PRECISION,
    premium_total           DOUBLE PRECISION,
    implied_vol             DOUBLE PRECISION,
    iv_rank                 DOUBLE PRECISION,
    delta                   DOUBLE PRECISION,
    underlying_price        DOUBLE PRECISION,
    detection_method        VARCHAR(30),

    -- Context at time of detection
    underlying_return_1d    DOUBLE PRECISION,
    underlying_return_5d    DOUBLE PRECISION,   -- prior 5d (momentum)
    iv_hv_ratio             DOUBLE PRECISION,
    put_call_ratio_1d       DOUBLE PRECISION,
    days_to_earnings        INT,
    vix_at_detection        DOUBLE PRECISION,
    spy_return_5d           DOUBLE PRECISION,

    -- Follow-through (filled in by nightly update job)
    underlying_return_1d_fwd    DOUBLE PRECISION,
    underlying_return_2d_fwd    DOUBLE PRECISION,
    underlying_return_5d_fwd    DOUBLE PRECISION,
    underlying_return_10d_fwd   DOUBLE PRECISION,
    underlying_max_fav_5d       DOUBLE PRECISION,  -- max favorable excursion
    underlying_max_adv_5d       DOUBLE PRECISION,  -- max adverse excursion
    option_mark_at_1d           DOUBLE PRECISION,
    option_mark_at_5d           DOUBLE PRECISION,
    option_return_5d            DOUBLE PRECISION,
    direction_correct           BOOLEAN,
    move_5d_exceeded_1pct       BOOLEAN,
    move_5d_exceeded_3pct       BOOLEAN,

    -- ML scoring (filled in by MarketAI after inference)
    ml_signal_score             DOUBLE PRECISION,
    ml_direction_score          DOUBLE PRECISION,
    ml_model_version            VARCHAR(50),
    ml_scored_at                TIMESTAMPTZ
);

CREATE INDEX idx_signal_catalog_symbol ON signal_catalog(symbol);
CREATE INDEX idx_signal_catalog_detected_at ON signal_catalog(detected_at);
```

### `signal_clusters`
When multiple contracts/expiries in the same ticker fire together,
cluster them into a single composite signal event.

```sql
CREATE TABLE signal_clusters (
    cluster_id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    detected_at             TIMESTAMPTZ NOT NULL,
    symbol                  VARCHAR(20) NOT NULL,
    contract_count          INT,
    call_count              INT,
    put_count               INT,
    dominant_expiry         DATE,
    dominant_type           CHAR(1),
    total_premium           DOUBLE PRECISION,
    max_single_premium      DOUBLE PRECISION,
    call_put_premium_ratio  DOUBLE PRECISION,  -- >1 = bullish flow
    strike_range_pct        DOUBLE PRECISION,  -- high-low / atm (tight=conviction)
    dte_range               INT,               -- max_dte - min_dte
    weighted_delta          DOUBLE PRECISION,  -- portfolio delta implied
    weighted_iv_rank        DOUBLE PRECISION,
    signal_ids              TEXT[],            -- references signal_catalog.id
    -- Follow-through
    underlying_return_5d_fwd DOUBLE PRECISION,
    cluster_correct         BOOLEAN
);
```

### `earnings_calendar`
```sql
CREATE TABLE earnings_calendar (
    symbol              VARCHAR(20),
    earnings_date       DATE,
    earnings_time       VARCHAR(5),   -- 'BMO' (before market open), 'AMC', 'UNKNOWN'
    fiscal_quarter      VARCHAR(10),
    expected_eps        DOUBLE PRECISION,
    actual_eps          DOUBLE PRECISION,
    eps_surprise_pct    DOUBLE PRECISION,
    expected_move_pct   DOUBLE PRECISION,  -- options-implied expected move
    actual_move_pct     DOUBLE PRECISION,
    updated_at          TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (symbol, earnings_date)
);
```

---

## Data Collection Scripts

### Collector 1: Chain Snapshot (every 5 minutes, market hours)

```python
# pseudocode — implement with schwab-py or httpx + Schwab OAuth2

async def collect_chain_snapshots():
    for symbol in get_active_watchlist():
        chain = await schwab_client.get_option_chain(
            symbol=symbol,
            include_quotes=True,
            option_type="ALL",
            range="ALL",
            expiration_month="ALL",
        )
        rows = normalize_chain_response(chain, snapshot_ts=now())
        questdb_ilp.write_batch("options_chain_snapshots", rows)
        
        # Immediately run unusual detection
        baseline = get_baseline(symbol)  # from postgres
        events = [r for r in rows if is_unusual(r, baseline)]
        if events:
            questdb_ilp.write_batch("options_unusual_volume_events", events)
            postgres.upsert_batch("signal_catalog", events)

# Schedule: every 5 minutes, 9:30–16:00 ET, Mon–Fri
```

### Collector 2: Intraday Bar Collector (real-time)

```python
async def collect_intraday_bars():
    for symbol in get_active_watchlist():
        bars = await schwab_client.get_price_history(
            symbol=symbol,
            period_type="day",
            period=1,
            frequency_type="minute",
            frequency=1,
            extended_hours_data=True,
        )
        questdb_ilp.write_batch("underlying_intraday_bars", 
                                normalize_bars(bars, resolution="1m"))
```

### Collector 3: IV Surface Snapshot (hourly)

```python
async def collect_iv_surface():
    for symbol in get_active_watchlist():
        chain = await schwab_client.get_option_chain(symbol=symbol)
        surface = compute_iv_surface(chain)  # compute ATM IV, skew, term structure
        questdb_ilp.write_batch("iv_surface_snapshots", surface)
```

### Collector 4: End-of-Day Summary Job (4:15pm ET nightly)

```python
async def eod_summary_job():
    for symbol in get_active_watchlist():
        # Aggregate today's chain snapshots → ticker_daily_summary
        summary = aggregate_daily_from_questdb(symbol, today())
        questdb_ilp.write("ticker_daily_summary", summary)
        
        # Recompute volume baseline from last 30 days
        baseline = compute_baseline_from_questdb(symbol, days=30)
        postgres.upsert("options_volume_baseline", baseline)
        
        # Fill in follow-through for 1d-old signals
        fill_followthrough(lag_days=1)
        fill_followthrough(lag_days=5)
        fill_followthrough(lag_days=10)
```

### Collector 5: Historical Backfill (one-time setup)

```python
# Pull last 2 years of daily OHLCV for all watchlist symbols
# Pull last 6 months of options chain EOD snapshots
# Compute baseline from historical data
# This seeds the signal_catalog with historical events for model training

async def historical_backfill(symbol: str, start_date: date, end_date: date):
    # 1. Daily underlying bars (2 years)
    bars = await schwab_client.get_price_history(
        symbol=symbol, period_type="year", period=2, 
        frequency_type="daily", frequency=1
    )
    questdb_ilp.write_batch("underlying_intraday_bars", normalize_bars(bars, "1d"))
    
    # 2. Options chain EOD snapshots (Schwab provides historical chain data)
    # Note: Schwab historical options data may be limited; supplement with
    # third-party if needed (CBOE, OptionsDX, etc.)
    for day in trading_days(start_date, end_date):
        chain = await schwab_client.get_option_chain(
            symbol=symbol, from_date=day, to_date=day
        )
        questdb_ilp.write_batch("options_chain_snapshots", normalize_chain(chain, day))
```

---

## ThinkScript Studies

### Study 1: Unusual Volume Scanner Config (use in TOS Scanner)

```thinkscript
# Study: UnusualOptionsVolume
# Use in Options Hacker (TOS Scanner) to get live unusual volume list
# Scan for: options with volume > 3x 20-day average, min 500 contracts

input volumeRatioThreshold = 3.0;
input minVolume = 500;
input minPremium = 50000;

def optionVolume = Volume();
def avgVolume20 = Average(Volume(), 20);
def volumeRatio = optionVolume / avgVolume20;
def mark = (bid() + ask()) / 2;
def premium = mark * optionVolume * 100;

plot unusualVolume = volumeRatio >= volumeRatioThreshold
                     and optionVolume >= minVolume
                     and premium >= minPremium;
```

### Study 2: IV Rank (add to chain for context)

```thinkscript
# IVRank: position of current IV in 52-week range
input length = 252;  # one year of trading days

def impliedVol = imp_volatility();
def ivHigh = Highest(impliedVol, length);
def ivLow  = Lowest(impliedVol, length);

plot IVRank = if ivHigh - ivLow > 0
              then (impliedVol - ivLow) / (ivHigh - ivLow) * 100
              else 0;
IVRank.SetDefaultColor(Color.CYAN);
```

### Study 3: Multi-Strike Cluster Alert

```thinkscript
# Alert when multiple strikes in same expiry fire unusual volume simultaneously
# Add to a watchlist alert to trigger webhook

def unusualCount = Sum(
    if Volume() > 3 * Average(Volume(), 20) and Volume() > 500 then 1 else 0,
    1  # current bar
);

Alert(unusualCount >= 3, "Multi-strike cluster: " + GetSymbol(), Alert.BAR, Sound.CHIMES);
```

---

## MCP Tools to Expose

The TOS MCP server should expose these tools so Claude/MarketAI can query it:

```
get_unusual_volume_events(symbol?, start_ts, end_ts, min_ratio?, min_premium?)
get_chain_snapshot(symbol, ts?)
get_signal_catalog(symbol?, start_date, end_date)
get_signal_clusters(symbol?, start_date, end_date)
get_iv_surface(symbol, ts?)
get_ticker_daily_summary(symbol, start_date, end_date)
get_underlying_bars(symbol, resolution, start_ts, end_ts)
get_watchlist()
update_watchlist(symbol, active, priority)
get_earnings_calendar(symbol?, date_range?)
trigger_chain_snapshot(symbol)   -- on-demand, outside scheduler
get_volume_baseline(symbol, strike, expiry, option_type)
```

---

## Collection Schedule Summary

| Job | Frequency | Window | Source |
|-----|-----------|--------|--------|
| Chain snapshot + unusual detection | Every 5 min | 9:30–16:00 ET | Schwab API |
| Intraday bar collector (1m) | Every 1 min | 9:30–16:10 ET | Schwab API |
| IV surface snapshot | Every 60 min | 9:30–16:00 ET | Schwab API |
| EOD summary + baseline refresh | 4:15 PM ET daily | Post-market | QuestDB aggregation |
| Follow-through fill job | 4:30 PM ET daily | Post-market | QuestDB + Schwab |
| Earnings calendar refresh | Nightly | Off-hours | Schwab API |
| Historical backfill | One-time | On setup | Schwab API |

---

## What MarketAI Connects To

MarketAI's Python service adds two new DB connection configs:

```python
# In python-service/app/core/db.py — add alongside existing QuestDB connection:

TOS_QUESTDB_DSN = "postgresql://admin:quest@tos-questdb:9100/qdb"
TOS_POSTGRES_DSN = "postgresql://user:pass@tos-postgres:5433/tos"

# MarketAI reads from:
#   tos-questdb: options_unusual_volume_events, options_chain_snapshots,
#                iv_surface_snapshots, underlying_intraday_bars, ticker_daily_summary
#   tos-postgres: signal_catalog, signal_clusters, watchlist, earnings_calendar
```
