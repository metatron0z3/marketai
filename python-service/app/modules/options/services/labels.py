from datetime import timedelta

from app.core.db import get_db_connection


MOVE_THRESHOLD = 0.02  # 2% move qualifies as a significant event


def generate_labels(symbol: str, start_date: str, end_date: str) -> int:
    """
    For each options_features row, look up the equity price 24h later in trades_data.
    label_24h = 1 if abs move > MOVE_THRESHOLD, else 0.
    Never uses future IV, OI, or options prices.
    """
    conn = get_db_connection()
    cur = conn.cursor()

    # Fetch feature rows that still need labels
    cur.execute(
        """
        SELECT ts_event, symbol
        FROM options_features
        WHERE symbol = %s
          AND ts_event >= %s
          AND ts_event <= %s
          AND label_24h IS NULL
        ORDER BY ts_event
        """,
        (symbol, start_date, end_date),
    )
    feature_rows = cur.fetchall()
    if not feature_rows:
        cur.close()
        conn.close()
        return 0

    labeled = 0
    for ts_event, sym in feature_rows:
        # Current price: last trade at or before ts_event
        cur.execute(
            """
            SELECT last(price)
            FROM trades_data
            WHERE instrument_id = (
                SELECT instrument_id FROM trades_data WHERE instrument_id IS NOT NULL LIMIT 1
            )
              AND ts_event <= %s
            LIMIT 1
            """,
            (ts_event,),
        )
        row_now = cur.fetchone()

        # Future price: first trade 24h after ts_event
        future_ts = ts_event + timedelta(hours=24)
        cur.execute(
            """
            SELECT first(price)
            FROM trades_data
            WHERE ts_event >= %s
              AND ts_event <= %s
            LIMIT 1
            """,
            (future_ts, future_ts + timedelta(hours=1)),
        )
        row_future = cur.fetchone()

        if not row_now or not row_future or row_now[0] is None or row_future[0] is None:
            continue

        price_now = float(row_now[0])
        price_future = float(row_future[0])
        if price_now == 0:
            continue

        move = abs(price_future - price_now) / price_now
        label = 1 if move > MOVE_THRESHOLD else 0

        cur.execute(
            """
            UPDATE options_features
            SET label_24h = %s
            WHERE symbol = %s AND ts_event = %s
            """,
            (label, sym, ts_event),
        )
        labeled += 1

    conn.commit()
    cur.close()
    conn.close()
    return labeled
