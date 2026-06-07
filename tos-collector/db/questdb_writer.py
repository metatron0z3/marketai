"""
QuestDB writer — uses ILP (InfluxDB Line Protocol) over TCP for fast bulk writes.
Falls back to psycopg2 for schema creation and queries.

ILP is 10-100x faster than SQL INSERT for time-series data.
Use write_rows_ilp() for intraday hot path; use psycopg2 for backfill and queries.
"""
import logging
import os
from datetime import datetime

import psycopg2

log = logging.getLogger(__name__)

QUESTDB_HOST = os.getenv("TOS_QUESTDB_HOST", "localhost")
QUESTDB_PORT_PG = int(os.getenv("TOS_QUESTDB_PORT", "9100"))
QUESTDB_ILP_PORT = int(os.getenv("TOS_QUESTDB_ILP_PORT", "9009"))


def get_pg_conn():
    return psycopg2.connect(
        host=QUESTDB_HOST, port=QUESTDB_PORT_PG,
        database="qdb", user="admin",
        password=os.getenv("TOS_QUESTDB_PASS", "quest"),
    )


def write_chain_rows_bulk(rows: list[dict]) -> int:
    """
    Bulk insert chain snapshot rows into options_chain_snapshots via ILP.
    Returns number of rows written.
    """
    if not rows:
        return 0
    try:
        from questdb.ingress import Sender, TimestampNanos
        with Sender(QUESTDB_HOST, QUESTDB_ILP_PORT) as sender:
            for row in rows:
                ts = row["snapshot_ts"]
                if isinstance(ts, datetime):
                    ts_ns = int(ts.timestamp() * 1e9)
                else:
                    ts_ns = int(ts * 1e9)
                sender.row(
                    "options_chain_snapshots",
                    symbols={
                        "underlying_symbol": str(row["underlying_symbol"]),
                        "option_type":       str(row["option_type"]),
                    },
                    columns={
                        "expiry":          str(row["expiry"]),
                        "days_to_expiry":  int(row["days_to_expiry"]),
                        "strike":          float(row["strike"]),
                        "bid":             float(row.get("bid") or 0),
                        "ask":             float(row.get("ask") or 0),
                        "mark":            float(row.get("mark") or 0),
                        "volume":          int(row.get("volume") or 0),
                        "open_interest":   int(row.get("open_interest") or 0),
                        "delta":           float(row.get("delta") or 0),
                        "gamma":           float(row.get("gamma") or 0),
                        "theta":           float(row.get("theta") or 0),
                        "vega":            float(row.get("vega") or 0),
                        "implied_vol":     float(row.get("implied_vol") or 0),
                        "iv_rank":         float(row.get("iv_rank") or 0),
                        "underlying_price": float(row.get("underlying_price") or 0),
                        "ba_spread_pct":   float(row.get("ba_spread_pct") or 0),
                        "in_the_money":    bool(row.get("in_the_money") or False),
                    },
                    at=TimestampNanos(ts_ns),
                )
        log.info("ILP wrote %d chain rows", len(rows))
        return len(rows)
    except ImportError:
        return _write_chain_rows_pg(rows)


def _write_chain_rows_pg(rows: list[dict]) -> int:
    """Fallback: write via psycopg2 if questdb-py not installed."""
    conn = get_pg_conn()
    try:
        with conn.cursor() as cur:
            for row in rows:
                cur.execute("""
                    INSERT INTO options_chain_snapshots
                    (snapshot_ts, underlying_symbol, expiry, days_to_expiry,
                     strike, option_type, bid, ask, mark, volume, open_interest,
                     delta, gamma, theta, vega, implied_vol, iv_rank,
                     underlying_price, ba_spread_pct, in_the_money)
                    VALUES (%(snapshot_ts)s, %(underlying_symbol)s, %(expiry)s,
                            %(days_to_expiry)s, %(strike)s, %(option_type)s,
                            %(bid)s, %(ask)s, %(mark)s, %(volume)s, %(open_interest)s,
                            %(delta)s, %(gamma)s, %(theta)s, %(vega)s,
                            %(implied_vol)s, %(iv_rank)s, %(underlying_price)s,
                            %(ba_spread_pct)s, %(in_the_money)s)
                """, row)
        conn.commit()
        return len(rows)
    finally:
        conn.close()


def write_price_bars(bars: list[dict]) -> int:
    """Write OHLCV bars to underlying_intraday_bars."""
    if not bars:
        return 0
    try:
        from questdb.ingress import Sender, TimestampNanos
        with Sender(QUESTDB_HOST, QUESTDB_ILP_PORT) as sender:
            for bar in bars:
                ts = bar["ts"]
                ts_ns = int(ts.timestamp() * 1e9)
                sender.row(
                    "underlying_intraday_bars",
                    symbols={"symbol": str(bar["symbol"]), "bar_size": str(bar["bar_size"])},
                    columns={
                        "open":   float(bar["open"]),
                        "high":   float(bar["high"]),
                        "low":    float(bar["low"]),
                        "close":  float(bar["close"]),
                        "volume": int(bar["volume"]),
                    },
                    at=TimestampNanos(ts_ns),
                )
        return len(bars)
    except ImportError:
        log.warning("questdb-py not installed — skipping price bar write")
        return 0


def write_iv_surface(row: dict) -> None:
    """Write one IV surface snapshot."""
    try:
        from questdb.ingress import Sender, TimestampNanos
        ts_ns = int(row["snapshot_ts"].timestamp() * 1e9)
        with Sender(QUESTDB_HOST, QUESTDB_ILP_PORT) as sender:
            sender.row(
                "iv_surface_snapshots",
                symbols={"symbol": str(row["symbol"])},
                columns={
                    "atm_iv":         float(row.get("atm_iv") or 0),
                    "skew_25d":       float(row.get("skew_25d") or 0),
                    "term_slope":     float(row.get("term_slope") or 0),
                    "iv_rank":        float(row.get("iv_rank") or 0),
                    "iv_percentile":  float(row.get("iv_percentile") or 0),
                    "underlying_price": float(row.get("underlying_price") or 0),
                },
                at=TimestampNanos(ts_ns),
            )
    except ImportError:
        log.warning("questdb-py not installed — IV surface write skipped")
