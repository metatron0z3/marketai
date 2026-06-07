#!/usr/bin/env python3
"""
run_yfinance_backfill.py — standalone yfinance historical backfill

Runs two passes in sequence:
  Pass 1: 2026-03-31 → today   (extends existing 2025 data to present)
  Pass 2: 2024-01-01 → 2024-12-31  (full year of 2024)

Idempotent: checks existing timestamps per symbol before inserting.
Safe to re-run — duplicate bars will not be written.

Usage:
  nohup python3 run_yfinance_backfill.py >> yfinance_backfill.log 2>&1 &
"""

import sys
import time
from datetime import date, datetime, timezone

import psycopg2
import yfinance as yf

QUESTDB_HOST = "localhost"
QUESTDB_PORT = 8812

SYMBOLS = ["TSLA", "NVDA", "AAPL", "AMD", "META", "SPY", "QQQ"]

INSTRUMENT_ID_MAP = {
    "AAPL": 10001,
    "AMD":  10002,
    "META": 10003,
    "NVDA": 10004,
    "SPY":  15144,
    "QQQ":  13340,
    "TSLA": 16244,
}

PASSES = [
    {"label": "2025-present gap", "start": "2026-03-31", "end": str(date.today())},
    {"label": "2024 full year",   "start": "2024-01-01", "end": "2024-12-31"},
]


def log(msg: str):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def get_conn():
    return psycopg2.connect(
        host=QUESTDB_HOST, port=QUESTDB_PORT,
        user="admin", password="quest", database="qdb",
    )


def get_existing_timestamps(conn, symbol: str, start: str, end: str) -> set:
    """Return set of existing ts values (as date strings YYYY-MM-DD) for a symbol in range."""
    cur = conn.cursor()
    cur.execute(
        "SELECT ts FROM yf_ohlcv_daily WHERE symbol = %s AND ts >= %s AND ts <= %s",
        (symbol, start, end),
    )
    result = {str(row[0])[:10] for row in cur.fetchall()}
    cur.close()
    return result


def fetch_yfinance(symbol: str, start: str, end: str) -> list[dict]:
    ticker = yf.Ticker(symbol)
    hist = ticker.history(start=start, end=end, interval="1d", auto_adjust=False)
    if hist.empty:
        return []

    bars = []
    for ts, row in hist.iterrows():
        if hasattr(ts, "tzinfo") and ts.tzinfo is not None:
            ts_utc = ts.tz_convert("UTC").to_pydatetime().replace(tzinfo=None)
        else:
            ts_utc = ts.to_pydatetime().replace(tzinfo=None)

        bars.append({
            "ts":            ts_utc,
            "ts_date":       str(ts_utc)[:10],
            "instrument_id": INSTRUMENT_ID_MAP.get(symbol, 99999),
            "symbol":        symbol,
            "open":          float(row.get("Open",  0) or 0),
            "high":          float(row.get("High",  0) or 0),
            "low":           float(row.get("Low",   0) or 0),
            "close":         float(row.get("Close", 0) or 0),
            "volume":        int(row.get("Volume", 0) or 0),
            "adj_close":     float(row.get("Adj Close", row.get("Close", 0)) or 0),
        })
    return bars


def insert_bars(conn, bars: list[dict], existing: set) -> int:
    new_bars = [b for b in bars if b["ts_date"] not in existing]
    if not new_bars:
        return 0

    cur = conn.cursor()
    cur.executemany(
        """INSERT INTO yf_ohlcv_daily
           (ts, instrument_id, symbol, source, timeframe, open, high, low, close, volume, adj_close)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        [
            (b["ts"], b["instrument_id"], b["symbol"], "yfinance", "1d",
             b["open"], b["high"], b["low"], b["close"], b["volume"], b["adj_close"])
            for b in new_bars
        ],
    )
    conn.commit()
    cur.close()
    return len(new_bars)


def run_pass(label: str, start: str, end: str):
    log(f"=== Starting pass: {label} ({start} → {end}) ===")
    conn = get_conn()
    total_written = 0

    for symbol in SYMBOLS:
        try:
            existing = get_existing_timestamps(conn, symbol, start, end)
            bars = fetch_yfinance(symbol, start, end)

            if not bars:
                log(f"  {symbol}: no data returned from yfinance")
                continue

            written = insert_bars(conn, bars, existing)
            skipped = len(bars) - written
            log(f"  {symbol}: {written} bars written, {skipped} skipped (already present)")
            total_written += written

        except Exception as exc:
            log(f"  {symbol}: ERROR — {exc}")

        time.sleep(1)  # brief pause between symbols to be polite to Yahoo

    conn.close()
    log(f"=== Pass complete: {label} — {total_written} total bars written ===")
    return total_written


if __name__ == "__main__":
    log("yfinance historical backfill starting")
    log(f"Symbols: {', '.join(SYMBOLS)}")

    grand_total = 0
    for p in PASSES:
        written = run_pass(p["label"], p["start"], p["end"])
        grand_total += written
        log(f"Sleeping 5s between passes...")
        time.sleep(5)

    log(f"All passes complete. Grand total: {grand_total} bars written.")
