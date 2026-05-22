from datetime import timedelta

import pandas as pd

from app.core.db import get_db_connection

MOVE_THRESHOLD = 0.02


def generate_labels(symbol: str, start_date: str, end_date: str) -> int:
    """
    Label options_features rows with future equity move direction.
    label_24h = 1 if underlying moves >2% within 24h, else 0.

    Uses two batch queries instead of per-row queries to avoid N+1:
    1. Fetch all unlabeled feature timestamps for the window.
    2. Fetch all equity prices for the window + 25h buffer in one query.
    3. Align prices to feature timestamps via merge_asof in pandas.
    4. Batch-update labels with executemany.

    Never uses future IV, OI, or options prices — only trades_data equity prices.
    """
    conn = get_db_connection()
    cur = conn.cursor()

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

    feature_df = pd.DataFrame(feature_rows, columns=["ts_event", "symbol"])
    feature_df["ts_event"] = pd.to_datetime(feature_df["ts_event"], utc=True)

    # Fetch all equity prices for the window + 25h buffer in one query
    window_end = feature_df["ts_event"].max() + timedelta(hours=25)
    cur.execute(
        """
        SELECT ts_event, price
        FROM trades_data
        WHERE ts_event >= %s
          AND ts_event <= %s
        ORDER BY ts_event
        """,
        (start_date, window_end.isoformat()),
    )
    price_rows = cur.fetchall()
    cur.close()

    if not price_rows:
        conn.close()
        return 0

    equity_df = pd.DataFrame(price_rows, columns=["ts_event", "price"])
    equity_df["ts_event"] = pd.to_datetime(equity_df["ts_event"], utc=True)
    equity_df = equity_df.sort_values("ts_event").reset_index(drop=True)

    # Current price: last equity trade at or before each feature timestamp
    current = pd.merge_asof(
        feature_df.sort_values("ts_event"),
        equity_df.rename(columns={"price": "price_now"}),
        on="ts_event",
        direction="backward",
    )

    # Future price: first equity trade on or after ts_event + 24h
    feature_df["ts_future"] = feature_df["ts_event"] + timedelta(hours=24)
    future_lookup = feature_df[["ts_event", "ts_future"]].copy()
    future_lookup = future_lookup.rename(columns={"ts_future": "ts_event_future"})
    equity_for_future = equity_df.rename(columns={"ts_event": "ts_event_future", "price": "price_future"})

    future = pd.merge_asof(
        future_lookup.sort_values("ts_event_future"),
        equity_for_future,
        on="ts_event_future",
        direction="forward",
    )
    future = future.rename(columns={"ts_event_future": "ts_event_future_key"})

    merged = current.copy()
    merged["ts_future"] = feature_df["ts_future"].values
    merged = merged.merge(
        future[["ts_event", "price_future"]],
        on="ts_event",
        how="left",
    )

    merged = merged.dropna(subset=["price_now", "price_future"])
    merged = merged[merged["price_now"] != 0]

    merged["move"] = (merged["price_future"] - merged["price_now"]).abs() / merged["price_now"]
    merged["label_24h"] = (merged["move"] > MOVE_THRESHOLD).astype(int)

    if merged.empty:
        conn.close()
        return 0

    cur = conn.cursor()
    cur.executemany(
        "UPDATE options_features SET label_24h = %s WHERE symbol = %s AND ts_event = %s",
        [
            (int(row["label_24h"]), row["symbol"], row["ts_event"])
            for _, row in merged.iterrows()
        ],
    )
    conn.commit()
    labeled = len(merged)
    cur.close()
    conn.close()
    return labeled
