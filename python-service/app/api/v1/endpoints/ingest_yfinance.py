"""
ingest_yfinance.py — yfinance OHLCV ingest endpoint

Fetches daily (or intraday) bars from Yahoo Finance via yfinance and
inserts them into the yf_ohlcv_daily QuestDB table.

pip dependency: yfinance>=0.2.40  (in requirements.txt)
"""

import logging
import os
import requests
import psycopg2
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
router = APIRouter()

_QUESTDB_HOST = os.getenv("QUESTDB_HOST", "questdb")
_QUESTDB_HTTP  = f"http://{_QUESTDB_HOST}:9000"

# Must match schema_additions.sql seed rows and instruments.py KNOWN_SYMBOLS.
YFINANCE_SYMBOL_MAP = {
    "AAPL": 10001,
    "AMD":  10002,
    "META": 10003,
    "NVDA": 10004,
    "AMZN": 10005,
    "MSFT": 10006,
    "GLD":  10007,
    "TLT":  10008,
    "SPX":  10009,
    "SPY":  15144,
    "QQQ":  13340,
    "TSLA": 16244,
}

YFINANCE_TIMEFRAME_MAP = {
    "1d":   "1d",
    "1h":   "1h",
    "5min": "5m",
    "1min": "1m",
}


class YFinanceIngestRequest(BaseModel):
    symbols:    List[str] = Field(..., description="List of ticker symbols e.g. ['AAPL','AMD']")
    start_date: str       = Field(..., description="Start date YYYY-MM-DD")
    end_date:   str       = Field(..., description="End date YYYY-MM-DD")
    timeframe:  str       = Field("1d", description="Bar timeframe: '1d' | '1h' | '5min'")


class YFinanceIngestResponse(BaseModel):
    symbols_requested: List[str]
    symbols_ingested:  List[str]
    symbols_failed:    List[str]
    total_bars:        int
    message:           str


def _get_questdb_conn():
    return psycopg2.connect(
        host=_QUESTDB_HOST, port=8812, user="admin", password="quest", database="qdb"
    )


def _ensure_table():
    sql = """
    CREATE TABLE IF NOT EXISTS yf_ohlcv_daily (
        ts            TIMESTAMP,
        instrument_id INT,
        symbol        SYMBOL,
        source        SYMBOL,
        timeframe     SYMBOL,
        open          DOUBLE,
        high          DOUBLE,
        low           DOUBLE,
        close         DOUBLE,
        volume        LONG,
        adj_close     DOUBLE
    ) TIMESTAMP(ts) PARTITION BY MONTH;
    """
    try:
        requests.get(f"{_QUESTDB_HTTP}/exec", params={"query": sql}, timeout=10).raise_for_status()
    except Exception as exc:
        logger.error("Failed to ensure yf_ohlcv_daily table: %s", exc)
        raise


def _ensure_instrument_registered(symbol: str, instrument_id: int):
    try:
        resp = requests.get(f"{_QUESTDB_HTTP}/exec", params={"query": f"SELECT count() FROM instruments WHERE symbol = '{symbol}'"}, timeout=5)
        count = resp.json().get("dataset", [[0]])[0][0]
        if count == 0:
            insert_sql = f"INSERT INTO instruments VALUES (now(), '{symbol}', {instrument_id}, 'yfinance', '{symbol}', 'equity')"
            requests.get(f"{_QUESTDB_HTTP}/exec", params={"query": insert_sql}, timeout=5)
            logger.info("Registered new instrument: %s → %d", symbol, instrument_id)
    except Exception as exc:
        logger.warning("Could not register instrument %s: %s", symbol, exc)


def _insert_bars(bars: list[dict]) -> bool:
    if not bars:
        return True
    conn = cursor = None
    try:
        conn = _get_questdb_conn()
        cursor = conn.cursor()
        cursor.executemany(
            """INSERT INTO yf_ohlcv_daily
               (ts, instrument_id, symbol, source, timeframe, open, high, low, close, volume, adj_close)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            [(b["ts"], b["instrument_id"], b["symbol"], b["source"],
              b["timeframe"], b["open"], b["high"], b["low"],
              b["close"], b["volume"], b["adj_close"]) for b in bars],
        )
        conn.commit()
        return True
    except Exception as exc:
        logger.error("Insert error: %s", exc)
        if conn:
            conn.rollback()
        return False
    finally:
        if cursor: cursor.close()
        if conn:   conn.close()


@router.post("/", response_model=YFinanceIngestResponse)
async def ingest_yfinance(req: YFinanceIngestRequest):
    """
    Fetch OHLCV bars from Yahoo Finance and store in yf_ohlcv_daily.

    Example:
        {"symbols": ["TSLA","NVDA","AAPL"], "start_date": "2025-01-01", "end_date": "2026-03-31", "timeframe": "1d"}
    """
    try:
        import yfinance as yf
    except ImportError:
        raise HTTPException(status_code=500, detail="yfinance not installed — add 'yfinance>=0.2.40' to requirements.txt and rebuild.")

    yf_interval = YFINANCE_TIMEFRAME_MAP.get(req.timeframe, "1d")
    _ensure_table()

    ingested, failed = [], []
    total_bars = 0

    for raw_symbol in req.symbols:
        symbol = raw_symbol.upper().strip()

        if symbol not in YFINANCE_SYMBOL_MAP:
            next_id = max(YFINANCE_SYMBOL_MAP.values(), default=10000) + 1
            YFINANCE_SYMBOL_MAP[symbol] = next_id
            logger.info("Auto-assigned instrument_id %d to %s", next_id, symbol)

        instrument_id = YFINANCE_SYMBOL_MAP[symbol]
        _ensure_instrument_registered(symbol, instrument_id)

        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(
                start=req.start_date,
                end=req.end_date,
                interval=yf_interval,
                auto_adjust=False,
            )

            if hist.empty:
                logger.warning("No data returned for %s", symbol)
                failed.append(symbol)
                continue

            bars = []
            for ts, row in hist.iterrows():
                if hasattr(ts, "tzinfo") and ts.tzinfo is not None:
                    ts_utc = ts.tz_convert("UTC").to_pydatetime().replace(tzinfo=None)
                else:
                    ts_utc = ts.to_pydatetime().replace(tzinfo=None)

                bars.append({
                    "ts":            ts_utc,
                    "instrument_id": instrument_id,
                    "symbol":        symbol,
                    "source":        "yfinance",
                    "timeframe":     req.timeframe,
                    "open":          float(row.get("Open",  0) or 0),
                    "high":          float(row.get("High",  0) or 0),
                    "low":           float(row.get("Low",   0) or 0),
                    "close":         float(row.get("Close", 0) or 0),
                    "volume":        int(row.get("Volume", 0) or 0),
                    "adj_close":     float(row.get("Adj Close", row.get("Close", 0)) or 0),
                })

            if not _insert_bars(bars):
                raise RuntimeError("Insert failed")

            total_bars += len(bars)
            ingested.append(symbol)
            logger.info("Ingested %d bars for %s", len(bars), symbol)

        except Exception as exc:
            logger.error("Failed to ingest %s: %s", symbol, exc)
            failed.append(symbol)

    return YFinanceIngestResponse(
        symbols_requested=req.symbols,
        symbols_ingested=ingested,
        symbols_failed=failed,
        total_bars=total_bars,
        message=(
            f"Ingested {total_bars} bars for {len(ingested)} symbol(s)."
            + (f" Failed: {', '.join(failed)}." if failed else "")
        ),
    )


@router.get("/symbols")
async def get_supported_symbols():
    """Return all symbols with a pre-assigned yfinance instrument_id."""
    return [{"symbol": sym, "instrument_id": iid} for sym, iid in sorted(YFINANCE_SYMBOL_MAP.items())]
