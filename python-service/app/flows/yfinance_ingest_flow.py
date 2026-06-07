"""
yfinance_ingest_flow.py — daily OHLCV refresh for all registered equity symbols

Run once to bootstrap, then schedule via Prefect:
    python -m app.flows.yfinance_ingest_flow            # one-shot local run
    prefect deployment run 'yfinance-daily-refresh/...' # trigger via Prefect UI
"""

import os
from datetime import date, timedelta
from typing import Optional

from prefect import flow, task, get_run_logger

_QUESTDB_HOST = os.getenv("QUESTDB_HOST", "questdb")
_QUESTDB_HTTP  = f"http://{_QUESTDB_HOST}:9000"

# Symbols to keep fresh — extend this list as new symbols are ingested via Massive
DEFAULT_SYMBOLS = ["TSLA", "NVDA", "AAPL", "AMD", "META", "SPY", "QQQ"]


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------

@task(name="get-last-bar-date", retries=2, retry_delay_seconds=10)
def get_last_bar_date(symbol: str) -> Optional[str]:
    """Return the most recent date stored in yf_ohlcv_daily for this symbol."""
    import requests
    resp = requests.get(
        f"{_QUESTDB_HTTP}/exec",
        params={"query": f"SELECT max(ts) FROM yf_ohlcv_daily WHERE symbol = '{symbol}'"},
        timeout=10,
    )
    rows = resp.json().get("dataset", [])
    if rows and rows[0][0]:
        return rows[0][0][:10]  # YYYY-MM-DD
    return None


@task(name="fetch-and-store-yf", retries=3, retry_delay_seconds=30)
def fetch_and_store(symbol: str, start_date: str, end_date: str) -> int:
    """Fetch daily bars from Yahoo Finance and insert into yf_ohlcv_daily."""
    logger = get_run_logger()

    import yfinance as yf
    from app.api.v1.endpoints.ingest_yfinance import (
        _insert_bars, _ensure_instrument_registered, YFINANCE_SYMBOL_MAP,
    )

    instrument_id = YFINANCE_SYMBOL_MAP.get(symbol)
    if instrument_id is None:
        logger.warning("%s not in YFINANCE_SYMBOL_MAP — skipping", symbol)
        return 0

    _ensure_instrument_registered(symbol, instrument_id)

    hist = yf.Ticker(symbol).history(
        start=start_date, end=end_date, interval="1d", auto_adjust=False,
    )
    if hist.empty:
        logger.warning("%s: no data returned from yfinance for %s→%s", symbol, start_date, end_date)
        return 0

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
            "timeframe":     "1d",
            "open":          float(row.get("Open",  0) or 0),
            "high":          float(row.get("High",  0) or 0),
            "low":           float(row.get("Low",   0) or 0),
            "close":         float(row.get("Close", 0) or 0),
            "volume":        int(row.get("Volume", 0) or 0),
            "adj_close":     float(row.get("Adj Close", row.get("Close", 0)) or 0),
        })

    _insert_bars(bars)
    logger.info("%s: %d bars written (%s→%s)", symbol, len(bars), start_date, end_date)
    return len(bars)


# ---------------------------------------------------------------------------
# Flow
# ---------------------------------------------------------------------------

@flow(name="yfinance-daily-refresh", log_prints=True)
def yfinance_daily_refresh(
    symbols: list[str] = DEFAULT_SYMBOLS,
    end_date: str = str(date.today()),
    lookback_days: int = 5,
) -> dict[str, int]:
    """
    Refresh yfinance daily OHLCV bars for all registered symbols.

    For each symbol, finds the most recent date already stored and fetches
    from there forward.  lookback_days adds a small overlap window to catch
    any bars that were missing on the last run (e.g. late-publishing data).

    Safe to run daily — QuestDB's designated timestamp on yf_ohlcv_daily means
    duplicate timestamps are silently overwritten on insert.
    """
    logger = get_run_logger()
    results: dict[str, int] = {}

    for symbol in symbols:
        last = get_last_bar_date(symbol)
        if last:
            from_date = min(
                (date.fromisoformat(last) + timedelta(days=1)).isoformat(),
                (date.fromisoformat(end_date) - timedelta(days=lookback_days)).isoformat(),
            )
        else:
            from_date = "2025-01-01"  # bootstrap start

        if from_date >= end_date:
            logger.info("%s: already up to date (last=%s)", symbol, last)
            results[symbol] = 0
            continue

        results[symbol] = fetch_and_store(symbol, from_date, end_date)

    total = sum(results.values())
    logger.info("Done — %d new bars across %d symbols", total, len(symbols))
    return results


if __name__ == "__main__":
    yfinance_daily_refresh()
