"""
Prefect Flow — Intraday Chain Collection + Unusual Volume Detection.

Runs every 5 minutes during market hours (9:30–16:00 ET, weekdays).
For each tick:
  1. Pull chain snapshot for all watchlist tickers
  2. Detect unusual volume vs baselines
  3. Write events to signal_catalog (unlabeled)
  4. Hourly: update IV surface snapshots

Schedule registered in deploy.py.
"""
import logging
from datetime import datetime, timezone

from prefect import flow, get_run_logger, task

log = logging.getLogger(__name__)

WATCHLIST = [
    "TSLA", "NVDA", "SPY", "QQQ", "AAPL",
    "AMD", "META", "AMZN", "MSFT", "GLD", "TLT",
]


@task(name="snapshot_and_detect", retries=2, retry_delay_seconds=15)
def snapshot_and_detect(symbol: str, prev_snapshot: list[dict] | None = None) -> dict:
    """
    Pull one chain snapshot, detect unusual volume, write results.
    Returns summary dict with event count.
    """
    from collectors.chain_collector import collect_snapshot
    from db.postgres_writer import load_baselines, upsert_signals
    from db.questdb_writer import write_chain_rows_bulk
    from detectors.unusual_volume import detect_unusual_events

    logger = get_run_logger()

    rows = collect_snapshot(symbol)
    write_chain_rows_bulk(rows)

    baselines = load_baselines([symbol])
    events = detect_unusual_events(rows, baselines, prev_snapshot_rows=prev_snapshot)

    if events:
        upsert_signals(events)
        logger.info("%s: %d unusual events detected", symbol, len(events))

    return {"symbol": symbol, "chain_rows": len(rows), "events": len(events)}


@task(name="update_iv_surface", retries=1)
def update_iv_surface(symbol: str) -> None:
    from collectors.chain_collector import collect_iv_surface
    from db.questdb_writer import write_iv_surface

    surface = collect_iv_surface(symbol)
    if surface:
        write_iv_surface(surface)


@task(name="check_market_hours")
def check_market_hours() -> bool:
    """Returns True if current time is within regular market hours (ET)."""
    from zoneinfo import ZoneInfo
    now_et = datetime.now(tz=ZoneInfo("America/New_York"))
    if now_et.weekday() >= 5:
        return False
    market_open  = now_et.replace(hour=9,  minute=30, second=0, microsecond=0)
    market_close = now_et.replace(hour=16, minute=0,  second=0, microsecond=0)
    return market_open <= now_et <= market_close


@task(name="refresh_baselines_if_stale")
def refresh_baselines_if_stale() -> bool:
    """
    Check if baselines were updated within the last 8 days.
    If stale, trigger a lightweight refresh from the last 25 days of QuestDB data.
    Returns True if refresh was performed.
    """
    from db.postgres_writer import get_conn
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) FROM options_volume_baseline
                WHERE updated_at > NOW() - INTERVAL '8 days'
            """)
            fresh = cur.fetchone()[0]
        if fresh == 0:
            get_run_logger().warning("Baselines are stale — triggering refresh")
            from flows.eod_processing import baseline_refresh_flow
            baseline_refresh_flow()
            return True
        return False
    finally:
        conn.close()


@flow(
    name="tos_intraday_collection",
    description="5-minute chain snapshots + unusual volume detection during market hours",
    log_prints=True,
)
def intraday_collection_flow(force: bool = False) -> dict:
    """
    Args:
        force: Run even outside market hours (useful for testing).
    """
    logger = get_run_logger()
    in_hours = check_market_hours()

    if not in_hours and not force:
        logger.info("Outside market hours — skipping")
        return {"status": "skipped", "reason": "outside_market_hours"}

    refresh_baselines_if_stale()

    now = datetime.now(tz=timezone.utc)
    run_iv = now.minute < 5   # run IV surface update at the top of each hour

    results = []
    for symbol in WATCHLIST:
        result = snapshot_and_detect(symbol)
        results.append(result)
        if run_iv:
            update_iv_surface(symbol)

    total_events = sum(r["events"] for r in results)
    logger.info("Intraday tick: %d events across %d tickers", total_events, len(WATCHLIST))

    return {
        "status":       "ok",
        "tick_time":    now.isoformat(),
        "total_events": total_events,
        "iv_updated":   run_iv,
        "by_symbol":    results,
    }


if __name__ == "__main__":
    intraday_collection_flow(force=True)
