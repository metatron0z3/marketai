"""
Prefect Flow — Nightly Model Retrain.

Runs after EOD (when follow-through labels are populated by TOS MCP server).
Retrains all TOS ML models if enough new labeled data has accumulated.

Schedule: daily at 22:00 ET (see deployment configuration)
"""
import logging

from prefect import flow, get_run_logger, task

log = logging.getLogger(__name__)

MIN_NEW_ROWS = 20   # minimum new labeled rows to trigger retrain


@task(name="check_new_labels")
def check_new_labels() -> int:
    """Count labeled rows added since last retrain."""
    from app.modules.tos.db.tos_db import get_tos_postgres, tos_available
    logger = get_run_logger()
    if not tos_available():
        logger.warning("TOS unavailable — skipping label check")
        return 0
    conn = get_tos_postgres()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) FROM signal_catalog
                WHERE  underlying_return_5d_fwd IS NOT NULL
                  AND  updated_at > NOW() - INTERVAL '25 hours'
            """)
            count = cur.fetchone()[0]
        logger.info("New labeled rows in last 25h: %d", count)
        return int(count)
    finally:
        conn.close()


@task(name="retrain_signal_quality", retries=1)
def retrain_signal_quality():
    logger = get_run_logger()
    logger.info("Retraining SignalQualityModel...")
    from app.modules.tos.ml.training.train_signal_quality import run_training
    result = run_training()
    logger.info("SignalQuality result: %s", result)
    return result


@task(name="retrain_direction_models", retries=1)
def retrain_direction_models():
    logger = get_run_logger()
    logger.info("Retraining DirectionModels (C + P)...")
    from app.modules.tos.ml.training.train_direction import run_training
    result_c = run_training(option_type="C")
    result_p = run_training(option_type="P")
    logger.info("Direction C: %s | P: %s", result_c, result_p)
    return {"C": result_c, "P": result_p}


@task(name="retrain_magnitude_model", retries=1)
def retrain_magnitude_model():
    logger = get_run_logger()
    logger.info("Retraining MagnitudeModel...")
    from app.modules.tos.ml.training.train_magnitude import run_training
    result = run_training()
    logger.info("Magnitude result: %s", result)
    return result


@task(name="retrain_sequence_model", retries=1)
def retrain_sequence_model():
    logger = get_run_logger()
    logger.info("Retraining EventSequenceTransformer...")
    from app.modules.tos.ml.training.train_sequence import run_training
    result = run_training()
    logger.info("Sequence result: %s", result)
    return result


@task(name="invalidate_scorer_cache")
def invalidate_scorer_cache():
    """Force the ConvictionScorer singleton to reload on next request."""
    import app.modules.tos.ml.inference.conviction_scorer as module
    module._scorer = None
    get_run_logger().info("ConvictionScorer cache invalidated")


@flow(
    name="tos_nightly_retrain",
    description="Nightly retrain of all TOS unusual volume ML models",
    log_prints=True,
)
def nightly_retrain_flow(force: bool = False):
    """
    Args:
        force: Skip the new-label check and retrain regardless.
    """
    logger = get_run_logger()

    new_rows = check_new_labels()
    if not force and new_rows < MIN_NEW_ROWS:
        logger.info("Only %d new rows — skipping retrain (need %d)", new_rows, MIN_NEW_ROWS)
        return {"status": "skipped", "new_rows": new_rows}

    logger.info("Starting retrain with %d new labeled rows", new_rows)

    # Run the three tree-based models (independent, could be parallelized with
    # Prefect task runner but kept sequential to avoid RAM spikes on small hosts)
    sq_result  = retrain_signal_quality()
    dir_result = retrain_direction_models()
    mag_result = retrain_magnitude_model()

    # Sequence model last — uses the most memory (PyTorch)
    seq_result = retrain_sequence_model()

    invalidate_scorer_cache()

    return {
        "status":         "ok",
        "new_rows":       new_rows,
        "signal_quality": sq_result,
        "direction":      dir_result,
        "magnitude":      mag_result,
        "sequence":       seq_result,
    }


if __name__ == "__main__":
    nightly_retrain_flow()
