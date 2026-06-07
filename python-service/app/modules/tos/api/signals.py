"""
TOS Signals API — recent unusual volume events with conviction scores.
"""
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.modules.tos.db.tos_db import get_tos_postgres, tos_available

log = logging.getLogger(__name__)
router = APIRouter()


@router.get("/signals")
def get_signals(
    symbol: Optional[str] = Query(None, description="Filter by ticker"),
    min_conviction: float  = Query(0.0,  ge=0, le=1),
    limit: int             = Query(50,   ge=1, le=500),
    only_alerts: bool      = Query(False),
):
    """Recent unusual volume events, optionally filtered and conviction-ranked."""
    if not tos_available():
        raise HTTPException(503, "TOS database unavailable")

    conn = get_tos_postgres()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    sc.signal_id, sc.symbol, sc.detected_at,
                    sc.is_call, sc.option_type, sc.strike,
                    sc.days_to_expiry, sc.premium_total,
                    sc.volume_ratio_20d, sc.vol_oi_ratio,
                    sc.otm_pct, sc.is_sweep,
                    COALESCE(cs.conviction_score, 0)   AS conviction_score,
                    COALESCE(cs.quality_score, 0)      AS quality_score,
                    COALESCE(cs.direction_score, 0)    AS direction_score,
                    COALESCE(cs.magnitude_score, 0)    AS magnitude_score,
                    cs.regime,
                    -- follow-through (may be NULL for unresolved signals)
                    sc.underlying_return_1d_fwd,
                    sc.underlying_return_5d_fwd,
                    sc.direction_correct_5d
                FROM  signal_catalog sc
                LEFT JOIN conviction_scores cs ON sc.signal_id = cs.signal_id
                WHERE (%(symbol)s IS NULL OR sc.symbol = %(symbol)s)
                  AND COALESCE(cs.conviction_score, 0) >= %(min_conviction)s
                ORDER BY sc.detected_at DESC
                LIMIT %(limit)s
            """, {"symbol": symbol, "min_conviction": min_conviction, "limit": limit})
            rows = cur.fetchall()
            cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in rows]
    finally:
        conn.close()


@router.get("/signals/{signal_id}")
def get_signal(signal_id: str):
    """Fetch a single signal with full detail."""
    if not tos_available():
        raise HTTPException(503, "TOS database unavailable")

    conn = get_tos_postgres()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT sc.*, cs.conviction_score, cs.quality_score,
                       cs.direction_score, cs.magnitude_score,
                       cs.regime, cs.regime_multiplier, cs.scored_at
                FROM   signal_catalog sc
                LEFT JOIN conviction_scores cs ON sc.signal_id = cs.signal_id
                WHERE  sc.signal_id = %(sid)s
            """, {"sid": signal_id})
            row = cur.fetchone()
            if row is None:
                raise HTTPException(404, f"Signal {signal_id} not found")
            cols = [d[0] for d in cur.description]
        return dict(zip(cols, row))
    finally:
        conn.close()


@router.get("/signals/stats/summary")
def get_signal_stats(symbol: Optional[str] = Query(None)):
    """Aggregate stats: signal counts, average conviction, top tickers."""
    if not tos_available():
        raise HTTPException(503, "TOS database unavailable")

    conn = get_tos_postgres()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    sc.symbol,
                    COUNT(*)                                     AS total_signals,
                    AVG(COALESCE(cs.conviction_score, 0))        AS avg_conviction,
                    AVG(COALESCE(cs.quality_score, 0))           AS avg_quality,
                    SUM(CASE WHEN sc.is_call THEN 1 ELSE 0 END)  AS call_count,
                    SUM(CASE WHEN NOT sc.is_call THEN 1 ELSE 0 END) AS put_count,
                    MAX(sc.detected_at)                          AS last_signal_at
                FROM  signal_catalog sc
                LEFT JOIN conviction_scores cs ON sc.signal_id = cs.signal_id
                WHERE (%(symbol)s IS NULL OR sc.symbol = %(symbol)s)
                GROUP BY sc.symbol
                ORDER BY avg_conviction DESC
            """, {"symbol": symbol})
            rows = cur.fetchall()
            cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in rows]
    finally:
        conn.close()
