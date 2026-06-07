"""
Prefect Flow — Intraday Signal Scoring.

Runs every 15 minutes during market hours to score newly ingested signals.
Also runs once at EOD to score any unscored labeled signals.

Schedule: every 15 min 09:30–16:15 ET on weekdays
"""
import logging

from prefect import flow, get_run_logger, task

log = logging.getLogger(__name__)

SCORE_BATCH_SIZE = 200


@task(name="score_unscored_signals", retries=2, retry_delay_seconds=30)
def score_unscored_signals(limit: int = SCORE_BATCH_SIZE) -> dict:
    logger = get_run_logger()
    logger.info("Batch scoring up to %d unscored signals...", limit)
    from app.modules.tos.ml.inference.batch_score_signals import batch_score
    result = batch_score(limit=limit)
    logger.info("Batch score result: %s", result)
    return result


@task(name="run_squeeze_scan")
def run_squeeze_scan() -> list[dict]:
    """Run gamma squeeze detector on full watchlist and log alerts."""
    logger = get_run_logger()
    from app.modules.tos.ml.research.gamma_squeeze_detect import scan_watchlist
    signals = scan_watchlist()
    alerts = [s for s in signals if s.alert]
    if alerts:
        logger.warning("SQUEEZE ALERTS: %s", [s.symbol for s in alerts])
    else:
        logger.info("No squeeze alerts (highest score: %.3f)",
                    signals[0].score if signals else 0)
    return [s.to_dict() for s in alerts]


@task(name="run_granger_check")
def run_granger_check():
    """Lightweight Granger check — runs weekly, skip if results exist."""
    import os
    logger = get_run_logger()
    if os.path.exists("granger_causality_results.csv"):
        logger.info("Granger results exist — skipping")
        return
    from app.modules.tos.ml.research.granger_causality import run_all_symbols
    symbols = ["TSLA", "NVDA", "SPY", "AAPL", "AMD"]
    results = run_all_symbols(symbols, max_lag=3)
    if not results.empty:
        results.to_csv("granger_causality_results.csv", index=False)
        logger.info("Granger causality results saved (%d rows)", len(results))


@flow(
    name="tos_signal_scoring",
    description="Intraday scoring of TOS unusual volume signals",
    log_prints=True,
)
def signal_scoring_flow(
    run_squeeze: bool = True,
    limit: int = SCORE_BATCH_SIZE,
) -> dict:
    score_result  = score_unscored_signals(limit=limit)
    squeeze_alerts: list[dict] = []

    if run_squeeze:
        squeeze_alerts = run_squeeze_scan()

    return {
        "scoring":        score_result,
        "squeeze_alerts": squeeze_alerts,
    }


@flow(
    name="tos_eod_scoring",
    description="End-of-day full scoring pass after label population",
    log_prints=True,
)
def eod_scoring_flow():
    """Scores all unscored labeled signals after TOS MCP server fills follow-through."""
    logger = get_run_logger()
    logger.info("EOD scoring pass starting...")

    # Large batch — get all labeled but unscored
    result = score_unscored_signals(limit=2000)
    squeeze_alerts = run_squeeze_scan()
    run_granger_check()

    return {
        "scoring":        result,
        "squeeze_alerts": squeeze_alerts,
    }


if __name__ == "__main__":
    signal_scoring_flow()
