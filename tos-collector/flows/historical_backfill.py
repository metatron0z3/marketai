"""
Prefect Flow — One-Time Historical Backfill.

Run this ONCE after the API key goes live. It executes all Tier 1 and Tier 2
data collection in dependency order, ending with a labeled signal_catalog
ready for the first model training run.

Estimated total runtime: ~2 hours.

Usage:
    python -m flows.historical_backfill             # all tickers, 90d
    python -m flows.historical_backfill --symbol TSLA --days 90
    python -m flows.historical_backfill --dry-run   # log what would run, no API calls
"""
import logging
from datetime import date, timedelta

from prefect import flow, get_run_logger, task
from prefect.task_runners import SequentialTaskRunner

from config import WATCHLIST

log = logging.getLogger(__name__)

BACKFILL_DAYS        = 90    # chain history to pull (trading days)
PRICE_HISTORY_YEARS  = 2     # OHLCV daily lookback
HOURLY_BAR_MONTHS    = 6     # 1h bar lookback for RSI features
IV_SURFACE_DAYS      = 60    # IV surface historical window


# ---------------------------------------------------------------------------
# STEP 1 — Underlying price history
# ---------------------------------------------------------------------------

@task(name="backfill_price_history", retries=2, retry_delay_seconds=30)
def backfill_price_history(symbol: str, years: int = PRICE_HISTORY_YEARS) -> dict:
    logger = get_run_logger()
    from collectors.price_collector import collect_daily_ohlcv, collect_hourly_bars
    from db.questdb_writer import write_price_bars

    daily = collect_daily_ohlcv(symbol, years=years)
    n_daily = write_price_bars(daily)

    hourly = collect_hourly_bars(symbol, months=HOURLY_BAR_MONTHS)
    n_hourly = write_price_bars(hourly)

    logger.info("%s: wrote %d daily + %d hourly bars", symbol, n_daily, n_hourly)
    return {"symbol": symbol, "daily": n_daily, "hourly": n_hourly}


# ---------------------------------------------------------------------------
# STEP 2 — Historical chain snapshots (EOD, day by day)
# ---------------------------------------------------------------------------

@task(name="backfill_chain_day", retries=2, retry_delay_seconds=60)
def backfill_chain_day(symbol: str, as_of_date: str) -> int:
    from collectors.chain_collector import collect_snapshot
    from db.questdb_writer import write_chain_rows_bulk

    rows = collect_snapshot(symbol, as_of_date=as_of_date)
    return write_chain_rows_bulk(rows)


@task(name="backfill_chains_symbol", retries=1)
def backfill_chains_symbol(symbol: str, days: int = BACKFILL_DAYS) -> dict:
    logger = get_run_logger()
    from collectors.chain_collector import collect_snapshot
    from db.questdb_writer import write_chain_rows_bulk

    trading_days = _get_trading_days(days)
    total = 0
    for d in trading_days:
        rows = collect_snapshot(symbol, as_of_date=str(d))
        n = write_chain_rows_bulk(rows)
        total += n
        logger.info("%s %s: wrote %d contracts", symbol, d, n)

    logger.info("%s chain backfill complete: %d total rows across %d days",
                symbol, total, len(trading_days))
    return {"symbol": symbol, "total_rows": total, "days": len(trading_days)}


# ---------------------------------------------------------------------------
# STEP 3 — Compute volume baselines from collected chain history
# ---------------------------------------------------------------------------

@task(name="compute_baselines_symbol")
def compute_baselines_symbol(symbol: str) -> int:
    logger = get_run_logger()
    from db.questdb_writer import get_pg_conn as get_qdb_conn
    from db.postgres_writer import upsert_baselines
    from detectors.unusual_volume import compute_baselines

    # Pull all chain rows for this symbol from QuestDB
    qdb = get_qdb_conn()
    with qdb.cursor() as cur:
        cur.execute("""
            SELECT underlying_symbol, strike, option_type, expiry::text, volume,
                   snapshot_ts
            FROM   options_chain_snapshots
            WHERE  underlying_symbol = %(sym)s
            ORDER  BY snapshot_ts
        """, {"sym": symbol})
        rows = [
            {"underlying_symbol": r[0], "strike": r[1], "option_type": r[2],
             "expiry": r[3], "volume": r[4], "snapshot_ts": r[5]}
            for r in cur.fetchall()
        ]
    qdb.close()

    baselines = compute_baselines(rows)
    n = upsert_baselines(baselines)
    logger.info("%s: computed %d contract baselines", symbol, n)
    return n


# ---------------------------------------------------------------------------
# STEP 4 — Historical unusual volume detection
# ---------------------------------------------------------------------------

@task(name="detect_historical_uv_symbol")
def detect_historical_uv_symbol(symbol: str) -> int:
    logger = get_run_logger()
    from db.questdb_writer import get_pg_conn as get_qdb_conn
    from db.postgres_writer import load_baselines, upsert_signals
    from detectors.unusual_volume import detect_unusual_events

    baselines = load_baselines([symbol])
    if not baselines:
        logger.warning("%s: no baselines found — skipping UV detection", symbol)
        return 0

    qdb = get_qdb_conn()
    with qdb.cursor() as cur:
        # Group by snapshot_ts and detect per-snapshot
        cur.execute("""
            SELECT DISTINCT snapshot_ts::date AS snap_date
            FROM   options_chain_snapshots
            WHERE  underlying_symbol = %(sym)s
            ORDER  BY snap_date
        """, {"sym": symbol})
        dates = [str(r[0]) for r in cur.fetchall()]

    total_events = 0
    for snap_date in dates:
        with qdb.cursor() as cur:
            cur.execute("""
                SELECT underlying_symbol, strike, option_type, expiry::text,
                       days_to_expiry, volume, open_interest, mark, bid, ask,
                       delta, gamma, theta, vega, implied_vol, iv_rank,
                       underlying_price, ba_spread_pct, snapshot_ts, in_the_money
                FROM   options_chain_snapshots
                WHERE  underlying_symbol = %(sym)s
                  AND  snapshot_ts::date = %(d)s::date
            """, {"sym": symbol, "d": snap_date})
            rows = [dict(zip([d[0] for d in cur.description], row))
                    for row in cur.fetchall()]

        events = detect_unusual_events(rows, baselines)
        if events:
            upsert_signals(events)
            total_events += len(events)
            logger.info("%s %s: %d events detected", symbol, snap_date, len(events))

    qdb.close()
    logger.info("%s: %d total historical events written", symbol, total_events)
    return total_events


# ---------------------------------------------------------------------------
# STEP 5 — Follow-through label fill
# ---------------------------------------------------------------------------

@task(name="compute_historical_labels")
def compute_historical_labels() -> dict:
    logger = get_run_logger()
    from db.postgres_writer import get_conn as get_pg
    from db.questdb_writer import get_pg_conn as get_qdb
    from detectors.label_computer import compute_all_pending_labels

    pg  = get_pg()
    qdb = get_qdb()
    result = compute_all_pending_labels(pg, qdb)
    pg.close()
    qdb.close()
    logger.info("Label fill result: %s", result)
    return result


# ---------------------------------------------------------------------------
# STEP 6 — IV surface backfill (independent, runs in parallel with steps 3-4)
# ---------------------------------------------------------------------------

@task(name="backfill_iv_surface_symbol", retries=1)
def backfill_iv_surface_symbol(symbol: str, days: int = IV_SURFACE_DAYS) -> int:
    logger = get_run_logger()
    from collectors.chain_collector import collect_iv_surface
    from db.questdb_writer import write_iv_surface

    written = 0
    for d in _get_trading_days(days):
        surface = collect_iv_surface(symbol)  # uses live data; historical limited by API
        if surface:
            write_iv_surface(surface)
            written += 1

    logger.info("%s: wrote %d IV surface snapshots", symbol, written)
    return written


# ---------------------------------------------------------------------------
# STEP 7 — Earnings calendar
# ---------------------------------------------------------------------------

@task(name="init_earnings_calendar")
def init_earnings_calendar() -> int:
    logger = get_run_logger()
    from db.postgres_writer import upsert_earnings_calendar

    # Pull from yfinance as supplement to Schwab API
    import yfinance as yf
    entries = []
    for sym in WATCHLIST:
        try:
            ticker = yf.Ticker(sym)
            cal = ticker.calendar
            if cal is not None and not cal.empty:
                for _, row in cal.iterrows():
                    entries.append({
                        "symbol":        sym,
                        "earnings_date": str(row.get("Earnings Date", "")).split(" ")[0],
                        "confirmed":     True,
                        "eps_estimate":  row.get("EPS Estimate"),
                    })
        except Exception as e:
            logger.warning("yfinance earnings failed for %s: %s", sym, e)

    n = upsert_earnings_calendar([e for e in entries if e["earnings_date"]])
    logger.info("Earnings calendar: %d entries written", n)
    return n


# ---------------------------------------------------------------------------
# STEP 8 — Intraday bars (5m + 1m) — run last, future support/resistance pipeline
# ---------------------------------------------------------------------------

@task(name="backfill_intraday_bars_symbol", retries=2, retry_delay_seconds=30)
def backfill_intraday_bars_symbol(symbol: str, days_5m: int = 90, days_1m: int = 10) -> dict:
    """
    Pull 5-minute and 1-minute bars for a single symbol.

    5m bars: chunked over days_5m (Schwab API limit = 10 days/call, so this makes
             multiple requests). Builds the foundation for the future intraday
             support/resistance ML pipeline.
    1m bars: last days_1m only (10 day API max per call). Appended daily going forward.
    """
    logger = get_run_logger()
    from collectors.price_collector import collect_1min_bars, collect_5min_bars_chunked
    from db.questdb_writer import write_price_bars

    bars_5m = collect_5min_bars_chunked(symbol, total_days=days_5m)
    n_5m    = write_price_bars(bars_5m)

    bars_1m = collect_1min_bars(symbol, days=days_1m)
    n_1m    = write_price_bars(bars_1m)

    logger.info("%s: wrote %d 5m bars + %d 1m bars", symbol, n_5m, n_1m)
    return {"symbol": symbol, "bars_5m": n_5m, "bars_1m": n_1m}


# ---------------------------------------------------------------------------
# Master backfill flow
# ---------------------------------------------------------------------------

@flow(
    name="tos_historical_backfill",
    description="One-time historical data backfill — run once after API key is live",
    task_runner=SequentialTaskRunner(),   # sequential: each step unlocks next
    log_prints=True,
)
def historical_backfill_flow(
    symbols: list[str] | None = None,
    days: int = BACKFILL_DAYS,
    dry_run: bool = False,
) -> dict:
    logger = get_run_logger()
    targets = symbols or WATCHLIST

    if dry_run:
        logger.info("DRY RUN — no API calls or writes")
        logger.info("Would process: %s", targets)
        logger.info("Chain backfill: %d days per symbol (%d total API calls)",
                    days, len(targets) * days)
        return {"status": "dry_run", "symbols": targets, "days": days}

    logger.info("=" * 60)
    logger.info("STEP 1: Underlying price history (%d tickers, %dy OHLCV)",
                len(targets), PRICE_HISTORY_YEARS)
    price_results = [backfill_price_history(sym) for sym in targets]

    logger.info("=" * 60)
    logger.info("STEP 2: Options chain backfill (%d days EOD)", days)
    chain_results = [backfill_chains_symbol(sym, days=days) for sym in targets]

    logger.info("=" * 60)
    logger.info("STEP 3: Volume baseline computation")
    baseline_results = [compute_baselines_symbol(sym) for sym in targets]

    logger.info("=" * 60)
    logger.info("STEP 4: Historical unusual volume detection")
    uv_results = [detect_historical_uv_symbol(sym) for sym in targets]

    logger.info("=" * 60)
    logger.info("STEP 5: Follow-through label fill")
    label_result = compute_historical_labels()

    logger.info("=" * 60)
    logger.info("STEP 6: Earnings calendar")
    earnings_result = init_earnings_calendar()

    logger.info("=" * 60)
    logger.info("STEP 7: Intraday bars (5m + 1m) — future support/resistance pipeline")
    intraday_results = [backfill_intraday_bars_symbol(sym) for sym in targets]
    total_5m = sum(r["bars_5m"] for r in intraday_results)
    total_1m = sum(r["bars_1m"] for r in intraday_results)

    total_events = sum(uv_results)
    total_labeled = label_result.get("labeled_5d", 0)

    logger.info("=" * 60)
    logger.info("BACKFILL COMPLETE")
    logger.info("  Total unusual events detected: %d", total_events)
    logger.info("  Labeled (5d follow-through):   %d", total_labeled)
    logger.info("  5m bars written:               %d", total_5m)
    logger.info("  1m bars written:               %d", total_1m)
    logger.info("  Ready for first training run:  %s", total_labeled >= 100)

    return {
        "status":         "complete",
        "symbols":        targets,
        "total_events":   total_events,
        "labeled_5d":     total_labeled,
        "bars_5m":        total_5m,
        "bars_1m":        total_1m,
        "training_ready": total_labeled >= 100,
    }


def _get_trading_days(n: int) -> list[date]:
    """Return last n weekdays (Monday–Friday) ending yesterday."""
    days = []
    d = date.today() - timedelta(days=1)
    while len(days) < n:
        if d.weekday() < 5:
            days.append(d)
        d -= timedelta(days=1)
    return list(reversed(days))


if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default=None)
    parser.add_argument("--days",   type=int, default=BACKFILL_DAYS)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    syms = [args.symbol] if args.symbol else None
    historical_backfill_flow(symbols=syms, days=args.days, dry_run=args.dry_run)
