"""
Prefect Flows — End-of-Day Processing.

Three flows, all triggered after market close:

  eod_label_flow        (4:30 PM ET) — fill follow-through returns in signal_catalog
  baseline_refresh_flow (Sunday 20:00 ET) — recompute rolling 20d volume baselines
  earnings_refresh_flow (Sunday 20:30 ET) — refresh earnings calendar next 4 weeks
  trigger_marketai_flow (22:00 ET) — fire MarketAI nightly retrain if enough new data
"""
import logging

from prefect import flow, get_run_logger, task

log = logging.getLogger(__name__)

WATCHLIST = [
    "TSLA", "NVDA", "SPY", "QQQ", "AAPL",
    "AMD", "META", "AMZN", "MSFT", "GLD", "TLT",
]

MIN_NEW_LABELED_FOR_RETRAIN = 20


# ---------------------------------------------------------------------------
# EOD label fill — 4:30 PM ET daily
# ---------------------------------------------------------------------------

@task(name="fill_followthrough_labels", retries=2, retry_delay_seconds=60)
def fill_followthrough_labels() -> dict:
    from db.postgres_writer import get_conn as get_pg
    from db.questdb_writer import get_pg_conn as get_qdb
    from detectors.label_computer import compute_all_pending_labels

    logger = get_run_logger()
    pg  = get_pg()
    qdb = get_qdb()
    try:
        result = compute_all_pending_labels(pg, qdb)
        logger.info("Label fill: %s", result)
        return result
    finally:
        pg.close()
        qdb.close()


@task(name="eod_chain_snapshot")
def eod_chain_snapshot() -> dict:
    """Pull a final EOD snapshot at 15:55 ET for each ticker."""
    from collectors.chain_collector import collect_snapshot
    from db.questdb_writer import write_chain_rows_bulk

    total = 0
    for sym in WATCHLIST:
        rows = collect_snapshot(sym)
        total += write_chain_rows_bulk(rows)
    return {"total_rows": total}


@task(name="update_ticker_signal_stats")
def update_ticker_signal_stats() -> None:
    """
    Refresh per-ticker historical signal stats used as features:
      ticker_signal_hit_rate_30d, ticker_signal_count_30d,
      ticker_avg_return_5d_after, ticker_avg_premium_30d
    These are written back to signal_catalog as precomputed features
    so the feature builder doesn't need to do rolling lookups at inference time.
    """
    from db.postgres_writer import get_conn
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE signal_catalog sc
                SET
                    ticker_signal_hit_rate_30d = stats.hit_rate,
                    ticker_signal_count_30d    = stats.signal_count,
                    ticker_avg_return_5d_after = stats.avg_return,
                    ticker_avg_premium_30d     = stats.avg_premium
                FROM (
                    SELECT symbol,
                           AVG(CASE WHEN direction_correct_5d = 1 THEN 1.0 ELSE 0.0 END) AS hit_rate,
                           COUNT(*)                                                        AS signal_count,
                           AVG(underlying_return_5d_fwd)                                  AS avg_return,
                           AVG(premium_total)                                              AS avg_premium
                    FROM   signal_catalog
                    WHERE  detected_at > NOW() - INTERVAL '30 days'
                      AND  direction_correct_5d IS NOT NULL
                    GROUP  BY symbol
                ) stats
                WHERE sc.symbol = stats.symbol
                  AND sc.detected_at > NOW() - INTERVAL '1 day'
            """)
        conn.commit()
    finally:
        conn.close()


@flow(
    name="tos_eod_labels",
    description="4:30 PM ET — fill T+1/T+5 follow-through labels in signal_catalog",
    log_prints=True,
)
def eod_label_flow() -> dict:
    logger = get_run_logger()
    logger.info("EOD label flow starting...")

    snap_result  = eod_chain_snapshot()
    label_result = fill_followthrough_labels()
    update_ticker_signal_stats()

    labeled_today = label_result.get("labeled_5d", 0)
    logger.info("EOD complete: %d new 5d labels", labeled_today)
    return {"snap": snap_result, "labels": label_result}


# ---------------------------------------------------------------------------
# Baseline refresh — Sunday 20:00 ET
# ---------------------------------------------------------------------------

@task(name="recompute_baselines_all")
def recompute_baselines_all(lookback_days: int = 25) -> int:
    logger = get_run_logger()
    from db.postgres_writer import upsert_baselines
    from db.questdb_writer import get_pg_conn as get_qdb
    from detectors.unusual_volume import compute_baselines

    qdb = get_qdb()
    total = 0
    for sym in WATCHLIST:
        with qdb.cursor() as cur:
            cur.execute("""
                SELECT underlying_symbol, strike, option_type, expiry::text, volume
                FROM   options_chain_snapshots
                WHERE  underlying_symbol = %(sym)s
                  AND  snapshot_ts > NOW() - INTERVAL %(days)s DAY
                ORDER  BY snapshot_ts
            """, {"sym": sym, "days": lookback_days})
            rows = [
                {"underlying_symbol": r[0], "strike": r[1],
                 "option_type": r[2], "expiry": r[3], "volume": r[4]}
                for r in cur.fetchall()
            ]
        baselines = compute_baselines(rows)
        n = upsert_baselines(baselines)
        total += n
        logger.info("%s: %d baselines refreshed", sym, n)
    qdb.close()
    return total


@flow(
    name="tos_baseline_refresh",
    description="Sunday 20:00 ET — recompute rolling 20d volume baselines",
    log_prints=True,
)
def baseline_refresh_flow() -> dict:
    n = recompute_baselines_all()
    return {"baselines_updated": n}


# ---------------------------------------------------------------------------
# Earnings calendar refresh — Sunday 20:30 ET
# ---------------------------------------------------------------------------

@task(name="refresh_earnings_calendar")
def refresh_earnings_calendar() -> int:
    logger = get_run_logger()
    import yfinance as yf
    from db.postgres_writer import upsert_earnings_calendar

    entries = []
    for sym in WATCHLIST:
        try:
            ticker = yf.Ticker(sym)
            cal = ticker.calendar
            if cal is not None and not cal.empty:
                for _, row in cal.iterrows():
                    ed = str(row.get("Earnings Date", "")).split(" ")[0]
                    if ed:
                        entries.append({
                            "symbol":        sym,
                            "earnings_date": ed,
                            "confirmed":     True,
                            "eps_estimate":  row.get("EPS Estimate"),
                        })
        except Exception as e:
            logger.warning("yfinance earnings failed for %s: %s", sym, e)

    n = upsert_earnings_calendar(entries)
    logger.info("Earnings calendar refreshed: %d entries", n)
    return n


@flow(
    name="tos_earnings_refresh",
    description="Sunday 20:30 ET — refresh earnings calendar for next 4 weeks",
    log_prints=True,
)
def earnings_refresh_flow() -> dict:
    n = refresh_earnings_calendar()
    return {"entries_written": n}


# ---------------------------------------------------------------------------
# Trigger MarketAI nightly retrain — 22:00 ET
# Fires only if enough new labeled data has accumulated
# ---------------------------------------------------------------------------

@task(name="count_new_labeled_signals")
def count_new_labeled_signals() -> int:
    from db.postgres_writer import get_conn
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) FROM signal_catalog
                WHERE  direction_correct_5d IS NOT NULL
                  AND  updated_at > NOW() - INTERVAL '25 hours'
            """)
            return int(cur.fetchone()[0])
    finally:
        conn.close()


@task(name="trigger_marketai_retrain")
def trigger_marketai_retrain(new_rows: int) -> dict:
    """
    Fire MarketAI's nightly_retrain_flow via Prefect API.
    Both services share the same Prefect server (port 4200).
    """
    logger = get_run_logger()
    if new_rows < MIN_NEW_LABELED_FOR_RETRAIN:
        logger.info("Only %d new labeled rows — skipping retrain (need %d)",
                    new_rows, MIN_NEW_LABELED_FOR_RETRAIN)
        return {"status": "skipped", "new_rows": new_rows}

    try:
        from prefect.deployments import run_deployment
        flow_run = run_deployment(
            name="tos_nightly_retrain/nightly",
            parameters={"force": False},
            timeout=0,   # fire-and-forget; don't block
        )
        logger.info("Triggered MarketAI retrain: flow_run_id=%s", flow_run.id)
        return {"status": "triggered", "flow_run_id": str(flow_run.id), "new_rows": new_rows}
    except Exception as e:
        logger.warning("Could not trigger MarketAI retrain: %s", e)
        return {"status": "error", "error": str(e)}


@flow(
    name="tos_nightly_orchestration",
    description="22:00 ET — nightly orchestration: check new data, trigger MarketAI retrain",
    log_prints=True,
)
def nightly_orchestration_flow() -> dict:
    new_rows = count_new_labeled_signals()
    retrain  = trigger_marketai_retrain(new_rows)
    return {"new_labeled_rows": new_rows, "retrain": retrain}


if __name__ == "__main__":
    eod_label_flow()
