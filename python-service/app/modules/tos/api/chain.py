"""
TOS Chain API — current options chain snapshots and IV surface.
"""
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.modules.tos.db.tos_db import get_tos_postgres, get_tos_questdb, tos_available

log = logging.getLogger(__name__)
router = APIRouter()


@router.get("/chain/{symbol}")
def get_chain(
    symbol: str,
    expiry: Optional[str] = Query(None, description="Filter to specific expiry YYYY-MM-DD"),
    is_call: Optional[bool] = Query(None, description="True=calls, False=puts, None=both"),
):
    """Latest options chain snapshot for a ticker."""
    if not tos_available():
        raise HTTPException(503, "TOS database unavailable")

    conn = get_tos_postgres()
    try:
        with conn.cursor() as cur:
            query = """
                SELECT symbol, strike, expiry_date, is_call,
                       bid, ask, last, volume, open_interest,
                       delta, gamma, theta, vega, iv,
                       underlying_price, snapshot_time
                FROM   options_chain_snapshots
                WHERE  symbol = %(sym)s
                  AND  snapshot_time = (
                      SELECT MAX(snapshot_time)
                      FROM   options_chain_snapshots
                      WHERE  symbol = %(sym)s
                  )
                  AND (%(expiry)s IS NULL OR expiry_date = %(expiry)s::date)
                  AND (%(is_call)s IS NULL OR is_call = %(is_call)s)
                ORDER  BY expiry_date, strike
            """
            cur.execute(query, {"sym": symbol, "expiry": expiry, "is_call": is_call})
            rows = cur.fetchall()
            cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in rows]
    finally:
        conn.close()


@router.get("/iv-surface/{symbol}")
def get_iv_surface(symbol: str, limit: int = Query(1, ge=1, le=20)):
    """IV surface snapshots — ATM IV, skew, and term structure."""
    if not tos_available():
        raise HTTPException(503, "TOS database unavailable")

    conn = get_tos_questdb()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT snapshot_time, atm_iv, skew_25d, skew_10d,
                       term_slope, iv_rank, iv_percentile
                FROM   iv_surface_snapshots
                WHERE  symbol = %(sym)s
                ORDER  BY snapshot_time DESC
                LIMIT  %(limit)s
            """, {"sym": symbol, "limit": limit})
            rows = cur.fetchall()
            cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in rows]
    finally:
        conn.close()


@router.get("/unusual-volume/{symbol}")
def get_unusual_volume(
    symbol: str,
    days: int = Query(5, ge=1, le=30),
    min_volume_ratio: float = Query(2.0, ge=1.0),
):
    """Recent unusual volume events from TOS QuestDB."""
    if not tos_available():
        raise HTTPException(503, "TOS database unavailable")

    conn = get_tos_questdb()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT detected_at, symbol, option_type, strike,
                       expiry_date, volume, avg_volume_20d,
                       volume_ratio_20d, premium_total, is_sweep
                FROM   options_unusual_volume_events
                WHERE  symbol = %(sym)s
                  AND  detected_at > NOW() - INTERVAL %(days)s DAY
                  AND  volume_ratio_20d >= %(ratio)s
                ORDER  BY detected_at DESC
            """, {"sym": symbol, "days": days, "ratio": min_volume_ratio})
            rows = cur.fetchall()
            cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in rows]
    finally:
        conn.close()
