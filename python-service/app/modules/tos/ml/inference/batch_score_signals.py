"""
Nightly batch scorer — scores all unscored signals in signal_catalog
and writes conviction scores back to the conviction_scores table.

Runs as a Prefect task (called from signal_scoring_flow.py) or standalone:
    python -m app.modules.tos.ml.inference.batch_score_signals

Creates conviction_scores table if it doesn't exist.
"""
import logging
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras

from app.modules.tos.db.tos_db import get_tos_postgres, tos_available
from app.modules.tos.ml.inference.conviction_scorer import ConvictionScorer

log = logging.getLogger(__name__)

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS conviction_scores (
    signal_id           VARCHAR(64) PRIMARY KEY,
    symbol              VARCHAR(16) NOT NULL,
    option_type         CHAR(1)     NOT NULL,
    quality_score       FLOAT,
    direction_score     FLOAT,
    magnitude_score     FLOAT,
    regime              VARCHAR(32),
    regime_multiplier   FLOAT,
    conviction_score    FLOAT,
    sequence_quality    FLOAT,
    cluster_quality     FLOAT,
    scored_at           TIMESTAMP   NOT NULL DEFAULT NOW(),
    model_version       VARCHAR(64)
);
"""

UNSCORED_QUERY = """
SELECT sc.signal_id, sc.symbol, sc.option_type
FROM   signal_catalog sc
LEFT JOIN conviction_scores cs ON sc.signal_id = cs.signal_id
WHERE  cs.signal_id IS NULL
  AND  sc.underlying_return_5d_fwd IS NOT NULL   -- labeled only
ORDER  BY sc.detected_at DESC
LIMIT  %(limit)s
"""

UPSERT_SQL = """
INSERT INTO conviction_scores (
    signal_id, symbol, option_type,
    quality_score, direction_score, magnitude_score,
    regime, regime_multiplier, conviction_score,
    sequence_quality, cluster_quality,
    scored_at, model_version
) VALUES (
    %(signal_id)s, %(symbol)s, %(option_type)s,
    %(quality_score)s, %(direction_score)s, %(magnitude_score)s,
    %(regime)s, %(regime_multiplier)s, %(conviction_score)s,
    %(sequence_quality)s, %(cluster_quality)s,
    %(scored_at)s, %(model_version)s
)
ON CONFLICT (signal_id) DO UPDATE SET
    quality_score      = EXCLUDED.quality_score,
    direction_score    = EXCLUDED.direction_score,
    magnitude_score    = EXCLUDED.magnitude_score,
    regime             = EXCLUDED.regime,
    regime_multiplier  = EXCLUDED.regime_multiplier,
    conviction_score   = EXCLUDED.conviction_score,
    sequence_quality   = EXCLUDED.sequence_quality,
    cluster_quality    = EXCLUDED.cluster_quality,
    scored_at          = EXCLUDED.scored_at,
    model_version      = EXCLUDED.model_version
"""


def ensure_conviction_table(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(CREATE_TABLE_SQL)
    conn.commit()


def batch_score(
    limit: int = 500,
    model_version: str = "latest",
) -> dict:
    """
    Score up to `limit` unscored signals and write results to conviction_scores.

    Returns summary stats dict.
    """
    if not tos_available():
        log.warning("TOS database unavailable — skipping batch scoring")
        return {"status": "skipped", "reason": "tos_unavailable"}

    scorer = ConvictionScorer()
    scorer.load_models()

    conn = get_tos_postgres()
    try:
        ensure_conviction_table(conn)

        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(UNSCORED_QUERY, {"limit": limit})
            rows = cur.fetchall()

        log.info("Scoring %d unscored signals", len(rows))
        if not rows:
            return {"status": "ok", "scored": 0, "skipped": 0}

        scored = 0
        skipped = 0
        now = datetime.now(tz=timezone.utc)

        for row in rows:
            try:
                result = scorer.score(row["signal_id"])
                with conn.cursor() as cur:
                    cur.execute(UPSERT_SQL, {
                        "signal_id":        result.signal_id,
                        "symbol":           result.symbol,
                        "option_type":      result.option_type,
                        "quality_score":    result.quality_score,
                        "direction_score":  result.direction_score,
                        "magnitude_score":  result.magnitude_score,
                        "regime":           result.regime_name,
                        "regime_multiplier": result.regime_multiplier,
                        "conviction_score": result.conviction_score,
                        "sequence_quality": result.sequence_quality,
                        "cluster_quality":  result.cluster_quality,
                        "scored_at":        now,
                        "model_version":    model_version,
                    })
                conn.commit()
                scored += 1
            except Exception as exc:
                log.warning("Failed to score signal %s: %s", row["signal_id"], exc)
                conn.rollback()
                skipped += 1

        log.info("Batch scoring complete: scored=%d skipped=%d", scored, skipped)
        return {"status": "ok", "scored": scored, "skipped": skipped}

    finally:
        conn.close()


def main():
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--model-version", default="latest")
    args = parser.parse_args()
    result = batch_score(args.limit, args.model_version)
    print(result)


if __name__ == "__main__":
    main()
