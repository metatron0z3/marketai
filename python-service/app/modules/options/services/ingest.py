import os
import uuid
import threading
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

import psycopg2

from app.core.db import get_db_connection
from .greeks import calculate_greeks

# In-memory job store (same pattern as existing ingest.py)
_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()


def _new_job(filename: str) -> str:
    job_id = str(uuid.uuid4())
    with _jobs_lock:
        _jobs[job_id] = {
            "id": job_id,
            "filename": filename,
            "status": "pending",
            "records_processed": 0,
            "error": None,
            "start_time": datetime.now(timezone.utc).isoformat(),
            "end_time": None,
        }
    return job_id


def _update_job(job_id: str, **kwargs) -> None:
    with _jobs_lock:
        _jobs[job_id].update(kwargs)


def get_job(job_id: str) -> dict | None:
    return _jobs.get(job_id)


def list_jobs() -> list[dict]:
    return list(_jobs.values())


def infer_aggressor(price: float, bid: float, ask: float) -> str:
    if price >= ask:
        return "BUY"
    if price <= bid:
        return "SELL"
    return "MID"


def detect_sweeps(trades: list[dict]) -> list[dict]:
    """Mark trades as sweeps: same contract, ≥3 exchanges, same aggressor, within 500ms."""
    grouped: dict[tuple, list[dict]] = defaultdict(list)
    for t in trades:
        key = (t["symbol"], t["strike"], t["expiration"], t["put_call"], t["aggressor_side"])
        grouped[key].append(t)

    for key, group in grouped.items():
        group.sort(key=lambda x: x["ts_event"])
        for i, trade in enumerate(group):
            window = [
                g for g in group
                if abs((g["ts_event"] - trade["ts_event"]).total_seconds() * 1000) <= 500
            ]
            if len({w["exchange"] for w in window}) >= 3:
                trade["is_sweep"] = True
    return trades


def _bulk_insert(conn: Any, trades: list[dict]) -> None:
    if not trades:
        return
    cur = conn.cursor()
    sql = """
        INSERT INTO options_trades (
            ts_event, symbol, strike, expiration, put_call,
            price, size, bid, ask, trade_condition, exchange,
            iv, delta, gamma, vega, theta,
            open_interest, aggressor_side, is_sweep, premium
        ) VALUES (
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s
        )
    """
    rows = [
        (
            t["ts_event"], t["symbol"], t["strike"], t["expiration"], t["put_call"],
            t["price"], t["size"], t["bid"], t["ask"], t.get("trade_condition", ""),
            t.get("exchange", ""),
            t["iv"], t["delta"], t["gamma"], t["vega"], t["theta"],
            t.get("open_interest", 0), t["aggressor_side"], t.get("is_sweep", False),
            t["price"] * 100 * t["size"],
        )
        for t in trades
    ]
    cur.executemany(sql, rows)
    conn.commit()
    cur.close()


def process_opra_file(job_id: str, file_path: str) -> None:
    """Background worker: parse .dbn.zst → enrich → insert into options_trades."""
    _update_job(job_id, status="running")
    try:
        import databento as db

        store = db.DBNStore.from_file(file_path)
        trades: list[dict] = []

        for record in store:
            rtype = getattr(record, "rtype", None)
            # rtype 0 = MBP-1 trade, skip non-trade records
            if not hasattr(record, "price") or not hasattr(record, "size"):
                continue

            symbol = getattr(record, "instrument_id", "")
            price = getattr(record, "price", 0) / 1e9
            size = getattr(record, "size", 0)
            bid = getattr(record, "bid_px_00", 0) / 1e9 if hasattr(record, "bid_px_00") else 0.0
            ask = getattr(record, "ask_px_00", 0) / 1e9 if hasattr(record, "ask_px_00") else 0.0
            ts_event_ns = getattr(record, "ts_event", 0)
            ts_event = datetime.fromtimestamp(ts_event_ns / 1e9, tz=timezone.utc)

            greeks = calculate_greeks(
                price=price,
                strike=0.0,   # enriched from instrument definition in production
                expiration=ts_event.date(),
                put_call="CALL",
                underlying_price=price,
            )

            trade = {
                "ts_event": ts_event,
                "symbol": str(symbol),
                "strike": 0.0,
                "expiration": ts_event.date(),
                "put_call": "CALL",
                "price": price,
                "size": size,
                "bid": bid,
                "ask": ask,
                "trade_condition": "",
                "exchange": "",
                "open_interest": 0,
                "aggressor_side": infer_aggressor(price, bid, ask),
                "is_sweep": False,
                **greeks,
            }
            trades.append(trade)

        trades = detect_sweeps(trades)

        conn = get_db_connection()
        BATCH = 1000
        for i in range(0, len(trades), BATCH):
            _bulk_insert(conn, trades[i : i + BATCH])
            _update_job(job_id, records_processed=min(i + BATCH, len(trades)))
        conn.close()

        _update_job(
            job_id,
            status="completed",
            records_processed=len(trades),
            end_time=datetime.now(timezone.utc).isoformat(),
        )
    except Exception as exc:
        _update_job(
            job_id,
            status="error",
            error=str(exc),
            end_time=datetime.now(timezone.utc).isoformat(),
        )
    finally:
        try:
            os.remove(file_path)
        except OSError:
            pass
