from datetime import timedelta

import pandas as pd

from app.core.db import get_db_connection

MOVE_THRESHOLD = 0.05
HORIZON_DAYS = 28


def generate_whale_labels(
    symbol: str,
    start_date: str,
    end_date: str,
    data_source: str = "databento",
) -> int:
    """
    Label whale_features rows with a 4-week directional move flag.
    label_4w = 1 if the underlying moves >5% within 28 calendar days, else 0.

    Uses two batch queries + merge_asof to avoid N+1 queries.
    Only uses future equity prices — never future IV, OI, or options data.

    Args:
        data_source: "databento" reads close prices from trades_data (default).
                     "massive"   reads close prices from underlying_bars.
                     When using the Massive path, run_massive_ingest already extends
                     the underlying_bars window 30 days past end_date, so future
                     prices for the full 28-day horizon are available without a
                     separate ingest call.
    """
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT ts_event, symbol
        FROM whale_features
        WHERE symbol = %s
          AND ts_event >= %s
          AND ts_event <= %s
          AND label_4w IS NULL
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

    window_end = feature_df["ts_event"].max() + timedelta(days=HORIZON_DAYS + 1)

    if data_source == "massive":
        cur.execute(
            """
            SELECT ts_event, close AS price
            FROM underlying_bars
            WHERE symbol = %s
              AND ts_event >= %s
              AND ts_event <= %s
            ORDER BY ts_event
            """,
            (symbol, start_date, window_end.isoformat()),
        )
    else:
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

    current = pd.merge_asof(
        feature_df.sort_values("ts_event"),
        equity_df.rename(columns={"price": "price_now"}),
        on="ts_event",
        direction="backward",
    )

    feature_df["ts_future"] = feature_df["ts_event"] + timedelta(days=HORIZON_DAYS)
    future_lookup = feature_df[["ts_event", "ts_future"]].rename(
        columns={"ts_future": "ts_event_future"}
    )
    equity_for_future = equity_df.rename(
        columns={"ts_event": "ts_event_future", "price": "price_future"}
    )

    future = pd.merge_asof(
        future_lookup.sort_values("ts_event_future"),
        equity_for_future,
        on="ts_event_future",
        direction="forward",
    )

    merged = current.copy()
    merged = merged.merge(
        future[["ts_event", "price_future"]], on="ts_event", how="left"
    )

    merged = merged.dropna(subset=["price_now", "price_future"])
    merged = merged[merged["price_now"] != 0]

    merged["move"] = (merged["price_future"] - merged["price_now"]).abs() / merged["price_now"]
    merged["label_4w"] = (merged["move"] > MOVE_THRESHOLD).astype(int)

    if merged.empty:
        conn.close()
        return 0

    cur = conn.cursor()
    cur.executemany(
        "UPDATE whale_features SET label_4w = %s WHERE symbol = %s AND ts_event = %s",
        [
            (int(row["label_4w"]), row["symbol"], row["ts_event"])
            for _, row in merged.iterrows()
        ],
    )
    conn.commit()
    labeled = len(merged)
    cur.close()
    conn.close()
    return labeled
