import os
import threading
from collections import defaultdict
from datetime import datetime, timezone

from app.core.db import get_db_connection
from app.core.job_manager import create_job, update_job
from .greeks import calculate_greeks


def infer_aggressor(price: float, bid: float, ask: float) -> str:
    if price >= ask:
        return "BUY"
    if price <= bid:
        return "SELL"
    return "MID"


def detect_sweeps(trades: list[dict]) -> list[dict]:
    """
    Mark is_sweep=True when ≥3 distinct exchanges hit the same side on the
    same contract within 500ms — indicates urgency-driven multi-venue fill.
    """
    grouped: dict[tuple, list[dict]] = defaultdict(list)
    for t in trades:
        key = (t["symbol"], t["strike"], t["expiration"], t["put_call"], t["aggressor_side"])
        grouped[key].append(t)

    for group in grouped.values():
        group.sort(key=lambda x: x["ts_event"])
        for i, trade in enumerate(group):
            j = i + 1
            window = [trade]
            while j < len(group):
                delta_ms = (group[j]["ts_event"] - trade["ts_event"]).total_seconds() * 1000
                if delta_ms > 500:
                    break
                window.append(group[j])
                j += 1
            if len({w["exchange"] for w in window}) >= 3:
                trade["is_sweep"] = True
    return trades


def _bulk_insert(conn, trades: list[dict]) -> None:
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
            t["price"], t["size"], t["bid"], t["ask"],
            t.get("trade_condition", ""), t.get("exchange", ""),
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
    update_job(job_id, status="running")
    try:
        import databento as db_lib

        store = db_lib.DBNStore.from_file(file_path)
        trades: list[dict] = []

        for record in store:
            if not hasattr(record, "price") or not hasattr(record, "size"):
                continue

            symbol = str(getattr(record, "instrument_id", ""))
            price = getattr(record, "price", 0) / 1e9
            size = getattr(record, "size", 0)
            bid = getattr(record, "bid_px_00", 0) / 1e9 if hasattr(record, "bid_px_00") else 0.0
            ask = getattr(record, "ask_px_00", 0) / 1e9 if hasattr(record, "ask_px_00") else 0.0
            ts_event_ns = getattr(record, "ts_event", 0)
            ts_event = datetime.fromtimestamp(ts_event_ns / 1e9, tz=timezone.utc)

            greeks = calculate_greeks(
                price=price,
                strike=0.0,
                expiration=ts_event.date(),
                put_call="CALL",
                underlying_price=price,
            )

            trades.append({
                "ts_event": ts_event,
                "symbol": symbol,
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
            })

        trades = detect_sweeps(trades)

        conn = get_db_connection()
        BATCH = 1000
        for i in range(0, len(trades), BATCH):
            _bulk_insert(conn, trades[i : i + BATCH])
            update_job(job_id, records_processed=min(i + BATCH, len(trades)))
        conn.close()

        update_job(
            job_id,
            status="completed",
            records_processed=len(trades),
            end_time=datetime.now(timezone.utc).isoformat(),
        )
    except Exception as exc:
        update_job(
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
