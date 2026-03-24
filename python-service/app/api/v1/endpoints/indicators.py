import logging
from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from ....services.ohlcv import fetch_ohlcv
from ....services.indicators import (
    calc_rsi,
    calc_vwap,
    calc_ma,
    calc_bollinger_bands,
    calc_volume,
    df_to_records,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/rsi")
async def get_rsi(
    instrument_id: int = Query(...),
    timeframe: str = Query("5min"),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
):
    """Get RSI (14-period) for an instrument."""
    try:
        period = 14
        df = fetch_ohlcv(instrument_id, timeframe, start_date, end_date)
        if df.empty:
            return {
                "meta": {
                    "instrument_id": instrument_id,
                    "timeframe": timeframe,
                    "period": period,
                    "insufficient_data": True,
                },
                "data": [],
            }
        result_df = calc_rsi(df, period)
        records = df_to_records(result_df, ["rsi"])
        insufficient = all(r["rsi"] is None for r in records)
        return {
            "meta": {
                "instrument_id": instrument_id,
                "timeframe": timeframe,
                "period": period,
                "insufficient_data": insufficient,
            },
            "data": records,
        }
    except Exception as e:
        logger.exception("Error computing RSI")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/vwap")
async def get_vwap(
    instrument_id: int = Query(...),
    timeframe: str = Query("5min"),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
):
    """Get VWAP (Volume Weighted Average Price) for an instrument."""
    try:
        df = fetch_ohlcv(instrument_id, timeframe, start_date, end_date)
        if df.empty:
            return {
                "meta": {
                    "instrument_id": instrument_id,
                    "timeframe": timeframe,
                    "insufficient_data": True,
                },
                "data": [],
            }
        result_df = calc_vwap(df)
        records = df_to_records(result_df, ["vwap"])
        insufficient = all(r["vwap"] is None for r in records)
        return {
            "meta": {
                "instrument_id": instrument_id,
                "timeframe": timeframe,
                "insufficient_data": insufficient,
            },
            "data": records,
        }
    except Exception as e:
        logger.exception("Error computing VWAP")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ma200")
async def get_ma200(
    instrument_id: int = Query(...),
    timeframe: str = Query("5min"),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
):
    """Get 200-period Moving Average for an instrument."""
    try:
        period = 200
        df = fetch_ohlcv(instrument_id, timeframe, start_date, end_date)
        if df.empty:
            return {
                "meta": {
                    "instrument_id": instrument_id,
                    "timeframe": timeframe,
                    "period": period,
                    "insufficient_data": True,
                },
                "data": [],
            }
        result_df = calc_ma(df, period)
        records = df_to_records(result_df, ["ma"])
        insufficient = all(r["ma"] is None for r in records)
        return {
            "meta": {
                "instrument_id": instrument_id,
                "timeframe": timeframe,
                "period": period,
                "insufficient_data": insufficient,
            },
            "data": records,
        }
    except Exception as e:
        logger.exception("Error computing MA200")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ma20")
async def get_ma20(
    instrument_id: int = Query(...),
    timeframe: str = Query("5min"),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
):
    """Get 20-period Moving Average for an instrument."""
    try:
        period = 20
        df = fetch_ohlcv(instrument_id, timeframe, start_date, end_date)
        if df.empty:
            return {
                "meta": {
                    "instrument_id": instrument_id,
                    "timeframe": timeframe,
                    "period": period,
                    "insufficient_data": True,
                },
                "data": [],
            }
        result_df = calc_ma(df, period)
        records = df_to_records(result_df, ["ma"])
        insufficient = all(r["ma"] is None for r in records)
        return {
            "meta": {
                "instrument_id": instrument_id,
                "timeframe": timeframe,
                "period": period,
                "insufficient_data": insufficient,
            },
            "data": records,
        }
    except Exception as e:
        logger.exception("Error computing MA20")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ma7")
async def get_ma7(
    instrument_id: int = Query(...),
    timeframe: str = Query("5min"),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
):
    """Get 7-period Moving Average for an instrument."""
    try:
        period = 7
        df = fetch_ohlcv(instrument_id, timeframe, start_date, end_date)
        if df.empty:
            return {
                "meta": {
                    "instrument_id": instrument_id,
                    "timeframe": timeframe,
                    "period": period,
                    "insufficient_data": True,
                },
                "data": [],
            }
        result_df = calc_ma(df, period)
        records = df_to_records(result_df, ["ma"])
        insufficient = all(r["ma"] is None for r in records)
        return {
            "meta": {
                "instrument_id": instrument_id,
                "timeframe": timeframe,
                "period": period,
                "insufficient_data": insufficient,
            },
            "data": records,
        }
    except Exception as e:
        logger.exception("Error computing MA7")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/bollinger-bands")
async def get_bollinger_bands(
    instrument_id: int = Query(...),
    timeframe: str = Query("5min"),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
):
    """Get Bollinger Bands (20-period, 2 std dev) for an instrument."""
    try:
        period = 20
        std_dev = 2.0
        df = fetch_ohlcv(instrument_id, timeframe, start_date, end_date)
        if df.empty:
            return {
                "meta": {
                    "instrument_id": instrument_id,
                    "timeframe": timeframe,
                    "period": period,
                    "std_dev": std_dev,
                    "insufficient_data": True,
                },
                "data": [],
            }
        result_df = calc_bollinger_bands(df, period, std_dev)
        records = df_to_records(result_df, ["middle", "upper", "lower"])
        insufficient = all(r["middle"] is None for r in records)
        return {
            "meta": {
                "instrument_id": instrument_id,
                "timeframe": timeframe,
                "period": period,
                "std_dev": std_dev,
                "insufficient_data": insufficient,
            },
            "data": records,
        }
    except Exception as e:
        logger.exception("Error computing Bollinger Bands")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/volume")
async def get_volume(
    instrument_id: int = Query(...),
    timeframe: str = Query("5min"),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
):
    """Get per-candle volume for an instrument."""
    try:
        df = fetch_ohlcv(instrument_id, timeframe, start_date, end_date)
        if df.empty:
            return {
                "meta": {
                    "instrument_id": instrument_id,
                    "timeframe": timeframe,
                    "insufficient_data": True,
                },
                "data": [],
            }
        result_df = calc_volume(df)
        records = df_to_records(result_df, ["volume"])
        return {
            "meta": {
                "instrument_id": instrument_id,
                "timeframe": timeframe,
                "insufficient_data": False,
            },
            "data": records,
        }
    except Exception as e:
        logger.exception("Error computing Volume")
        raise HTTPException(status_code=500, detail=str(e))
