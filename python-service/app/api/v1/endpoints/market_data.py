"""
market_data.py — OHLCV endpoint with two-tier data lookup

Priority:
  1. trades_data  (Databento tick data — high-fidelity, any timeframe)
  2. yf_ohlcv_daily (yfinance daily bars)

If trades_data returns zero rows for an instrument, the endpoint transparently
falls back to yf_ohlcv_daily.  Both sources return the same response shape.
"""

import logging
from fastapi import APIRouter, HTTPException, Query
from typing import List, Dict, Optional, Union
from datetime import datetime
from ....core.db import get_db_connection

logger = logging.getLogger(__name__)
router = APIRouter()

TIMEFRAME_SAMPLE = {
    "5min":  "5m",
    "1hour": "1h",
    "1day":  "1d",
}


def _query_trades_data(instrument_id: int, sample: str, start: str | None, end: str | None) -> list:
    q = f"""
    SELECT
        ts_event        AS timestamp,
        instrument_id,
        first(price)    AS open,
        max(price)      AS high,
        min(price)      AS low,
        last(price)     AS close,
        sum(size)       AS volume
    FROM trades_data
    WHERE instrument_id = {instrument_id}
    """
    if start:
        q += f" AND ts_event >= '{start}T00:00:00.000000Z'"
    if end:
        q += f" AND ts_event <= '{end}T23:59:59.999999Z'"
    q += f" SAMPLE BY {sample} ALIGN TO CALENDAR"

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(q)
    cols = [d[0] for d in cursor.description]
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return _rows_to_dicts(cols, rows)


def _query_yf_ohlcv(instrument_id: int, timeframe: str, start: str | None, end: str | None) -> list:
    """Read pre-aggregated bars from yf_ohlcv_daily, falling back to '1d' if exact timeframe missing."""
    for tf in [timeframe, "1d"]:
        q = f"""
        SELECT
            ts              AS timestamp,
            instrument_id,
            open,
            high,
            low,
            close,
            volume
        FROM yf_ohlcv_daily
        WHERE instrument_id = {instrument_id}
          AND timeframe = '{tf}'
        """
        if start:
            q += f" AND ts >= '{start}T00:00:00.000000Z'"
        if end:
            q += f" AND ts <= '{end}T23:59:59.999999Z'"
        q += " ORDER BY ts ASC"

        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(q)
            cols = [d[0] for d in cursor.description]
            rows = cursor.fetchall()
            cursor.close()
            conn.close()
            if rows:
                return _rows_to_dicts(cols, rows)
        except Exception as exc:
            logger.warning("yf_ohlcv_daily query failed for tf=%s: %s", tf, exc)

    return []


def _rows_to_dicts(cols: list, rows: list) -> list:
    result = []
    for row in rows:
        rec = {}
        for i, col in enumerate(cols):
            val = row[i]
            if col == "timestamp" and val:
                rec[col] = val.isoformat() + "Z" if isinstance(val, datetime) else str(val)
            else:
                rec[col] = val
        result.append(rec)
    return result


@router.get("/")
async def get_market_data(
    instrument_id: int = Query(..., description="The instrument ID to query"),
    timeframe: str = Query("5min", description="Aggregation timeframe: '5min', '1hour', or '1day'"),
    start_date: Optional[str] = Query(None, description="Start date YYYY-MM-DD"),
    end_date:   Optional[str] = Query(None, description="End date YYYY-MM-DD"),
) -> List[Dict[str, Union[str, int, float, None]]]:
    """
    Fetch aggregated OHLCV data.

    Tries trades_data (tick-level) first; if empty, falls back to yf_ohlcv_daily.
    Both sources return the same response shape.
    """
    sample = TIMEFRAME_SAMPLE.get(timeframe, "5m")
    logger.info("market_data: instrument=%d timeframe=%s start=%s end=%s", instrument_id, timeframe, start_date, end_date)

    try:
        result = _query_trades_data(instrument_id, sample, start_date, end_date)
        if result:
            logger.info("Returning %d rows from trades_data", len(result))
            return result
        logger.info("trades_data empty for instrument %d — trying yf_ohlcv_daily", instrument_id)
    except Exception as exc:
        logger.warning("trades_data query failed: %s — falling back to yf_ohlcv_daily", exc)

    try:
        result = _query_yf_ohlcv(instrument_id, timeframe, start_date, end_date)
        if result:
            logger.info("Returning %d rows from yf_ohlcv_daily (fallback)", len(result))
            return result
    except Exception as exc:
        logger.error("yf_ohlcv_daily query also failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Database query error: {exc}")

    return []
