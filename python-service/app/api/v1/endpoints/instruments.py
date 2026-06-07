"""
instruments.py — dynamic instrument registry

Two-layer lookup:
  1. KNOWN_SYMBOLS (in-process fallback, always available)
  2. QuestDB instruments table (authoritative, grows as data is ingested)
"""

import logging
import os
import requests
from fastapi import APIRouter, HTTPException
from typing import List, Dict, Union

logger = logging.getLogger(__name__)
router = APIRouter()

_QUESTDB_HOST = os.getenv("QUESTDB_HOST", "questdb")
_QUESTDB_HTTP  = f"http://{_QUESTDB_HOST}:9000"

# ---------------------------------------------------------------------------
# Fallback map — used when QuestDB is unavailable or table is empty.
# Keep in sync with schema_additions.sql seed rows.
# ---------------------------------------------------------------------------
KNOWN_SYMBOLS: Dict[str, dict] = {
    # Databento IDs
    "SPY":  {"id": 15144, "source": "databento", "name": "SPDR S&P 500 ETF",          "asset_class": "etf"},
    "QQQ":  {"id": 13340, "source": "databento", "name": "Invesco QQQ ETF",            "asset_class": "etf"},
    "TSLA": {"id": 16244, "source": "databento", "name": "Tesla Inc.",                  "asset_class": "equity"},
    # yfinance IDs
    "AAPL": {"id": 10001, "source": "yfinance",  "name": "Apple Inc.",                  "asset_class": "equity"},
    "AMD":  {"id": 10002, "source": "yfinance",  "name": "Advanced Micro Devices",      "asset_class": "equity"},
    "META": {"id": 10003, "source": "yfinance",  "name": "Meta Platforms Inc.",         "asset_class": "equity"},
    "NVDA": {"id": 10004, "source": "yfinance",  "name": "NVIDIA Corporation",          "asset_class": "equity"},
    "AMZN": {"id": 10005, "source": "yfinance",  "name": "Amazon.com Inc.",             "asset_class": "equity"},
    "MSFT": {"id": 10006, "source": "yfinance",  "name": "Microsoft Corporation",       "asset_class": "equity"},
    "GLD":  {"id": 10007, "source": "yfinance",  "name": "SPDR Gold Shares",            "asset_class": "etf"},
    "TLT":  {"id": 10008, "source": "yfinance",  "name": "iShares 20+ Year Treasury",   "asset_class": "etf"},
    "SPX":  {"id": 10009, "source": "yfinance",  "name": "S&P 500 Index",               "asset_class": "index"},
}

ID_TO_SYMBOL: Dict[int, str] = {v["id"]: k for k, v in KNOWN_SYMBOLS.items()}


def _query_questdb(sql: str) -> dict | None:
    try:
        resp = requests.get(f"{_QUESTDB_HTTP}/exec", params={"query": sql}, timeout=5)
        resp.raise_for_status()
        result = resp.json()
        if "error" in result:
            logger.warning("QuestDB query error: %s", result["error"])
            return None
        return result
    except Exception as exc:
        logger.warning("QuestDB unreachable: %s", exc)
        return None


def _load_from_questdb() -> List[Dict]:
    result = _query_questdb(
        "SELECT symbol, instrument_id, source, name, asset_class "
        "FROM instruments ORDER BY ts ASC"
    )
    if not result:
        return []

    cols = [c["name"] for c in result.get("columns", [])]
    seen: Dict[str, dict] = {}
    for row in result.get("dataset", []):
        rec = dict(zip(cols, row))
        seen[rec["symbol"]] = {
            "symbol":      rec["symbol"],
            "id":          rec["instrument_id"],
            "source":      rec.get("source", "unknown"),
            "name":        rec.get("name", ""),
            "asset_class": rec.get("asset_class", "equity"),
        }
    return list(seen.values())


@router.get("/", response_model=List[Dict[str, Union[str, int]]])
async def get_instruments():
    """Return all known instruments, merging QuestDB rows with the in-process fallback map."""
    db_rows = _load_from_questdb()

    merged: Dict[str, dict] = {k: {"symbol": k, **v} for k, v in KNOWN_SYMBOLS.items()}
    for row in db_rows:
        merged[row["symbol"]] = row

    return [
        {"symbol": sym, "id": info["id"], "name": info.get("name", ""), "source": info.get("source", "")}
        for sym, info in sorted(merged.items())
    ]


@router.get("/{symbol}")
async def get_instrument_by_symbol(symbol: str):
    """Look up a single instrument by ticker symbol."""
    symbol = symbol.upper()

    result = _query_questdb(
        f"SELECT symbol, instrument_id, source, name, asset_class "
        f"FROM instruments WHERE symbol = '{symbol}' ORDER BY ts DESC LIMIT 1"
    )
    if result and result.get("dataset"):
        row = result["dataset"][0]
        cols = [c["name"] for c in result["columns"]]
        rec = dict(zip(cols, row))
        return {"symbol": rec["symbol"], "id": rec["instrument_id"], "name": rec.get("name", ""), "source": rec.get("source", "")}

    if symbol in KNOWN_SYMBOLS:
        info = KNOWN_SYMBOLS[symbol]
        return {"symbol": symbol, "id": info["id"], "name": info.get("name", ""), "source": info.get("source", "")}

    raise HTTPException(status_code=404, detail=f"Instrument '{symbol}' not found")
