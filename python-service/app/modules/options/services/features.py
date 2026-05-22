from datetime import date, datetime, timezone

import pandas as pd

from app.core.db import get_db_connection


def compute_features(symbol: str, start_date: str, end_date: str) -> int:
    """Compute per-contract features from options_trades and write to options_features."""
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT
            ts_event, symbol, strike, expiration, put_call,
            price, size, bid, ask, exchange, iv, delta, gamma, vega, theta,
            open_interest, aggressor_side, is_sweep, premium
        FROM options_trades
        WHERE symbol = %s
          AND ts_event >= %s
          AND ts_event <= %s
        ORDER BY ts_event
        """,
        (symbol, start_date, end_date),
    )
    rows = cur.fetchall()
    if not rows:
        cur.close()
        conn.close()
        return 0

    cols = [
        "ts_event", "symbol", "strike", "expiration", "put_call",
        "price", "size", "bid", "ask", "exchange", "iv", "delta", "gamma", "vega", "theta",
        "open_interest", "aggressor_side", "is_sweep", "premium",
    ]
    df = pd.DataFrame(rows, columns=cols)
    df["ts_event"] = pd.to_datetime(df["ts_event"])
    df = df.sort_values("ts_event").reset_index(drop=True)

    # --- RVOL: current volume vs 20-day rolling average ---
    df["date"] = df["ts_event"].dt.date
    daily_vol = df.groupby(["symbol", "strike", "expiration", "put_call", "date"])["size"].sum().reset_index()
    daily_vol["avg_vol_20d"] = daily_vol.groupby(["symbol", "strike", "expiration", "put_call"])["size"].transform(
        lambda x: x.rolling(20, min_periods=1).mean().shift(1)
    )
    daily_vol["rvol"] = daily_vol["size"] / daily_vol["avg_vol_20d"].replace(0, 1)
    df = df.merge(daily_vol[["symbol", "strike", "expiration", "put_call", "date", "rvol"]], on=["symbol", "strike", "expiration", "put_call", "date"], how="left")

    # --- Vol/OI ---
    df["vol_oi_ratio"] = df["size"] / df["open_interest"].replace(0, 1)

    # --- Premium Flow ---
    df["premium_flow"] = df["premium"]

    # --- Sweep Intensity: sweeps / total trades in 5-min buckets ---
    df["bucket"] = df["ts_event"].dt.floor("5min")
    bucket_stats = df.groupby(["symbol", "strike", "expiration", "put_call", "bucket"]).agg(
        total=("size", "count"),
        sweeps=("is_sweep", "sum"),
    ).reset_index()
    bucket_stats["sweep_intensity"] = bucket_stats["sweeps"] / bucket_stats["total"].replace(0, 1)
    df = df.merge(bucket_stats[["symbol", "strike", "expiration", "put_call", "bucket", "sweep_intensity"]], on=["symbol", "strike", "expiration", "put_call", "bucket"], how="left")

    # --- Aggressor Ratio: buy premium / total premium ---
    df["buy_premium"] = df["premium"].where(df["aggressor_side"] == "BUY", 0)
    df["sell_premium"] = df["premium"].where(df["aggressor_side"] == "SELL", 0)
    agg_ratio = df.groupby(["symbol", "strike", "expiration", "put_call", "bucket"]).agg(
        buy_p=("buy_premium", "sum"),
        sell_p=("sell_premium", "sum"),
    ).reset_index()
    agg_ratio["aggressor_ratio"] = agg_ratio["buy_p"] / (agg_ratio["buy_p"] + agg_ratio["sell_p"]).replace(0, 1)
    df = df.merge(agg_ratio[["symbol", "strike", "expiration", "put_call", "bucket", "aggressor_ratio"]], on=["symbol", "strike", "expiration", "put_call", "bucket"], how="left")

    # --- Delta Exposure ---
    df["delta_exposure"] = df["delta"] * df["size"] * 100

    # --- IV Rank ---
    iv_stats = df.groupby(["symbol", "strike", "expiration", "put_call"])["iv"].agg(
        iv_low="min", iv_high="max"
    ).reset_index()
    df = df.merge(iv_stats, on=["symbol", "strike", "expiration", "put_call"], how="left")
    iv_range = (df["iv_high"] - df["iv_low"]).replace(0, 1)
    df["iv_rank"] = (df["iv"] - df["iv_low"]) / iv_range

    # --- Days to Expiration ---
    today = date.today()
    df["days_to_exp"] = df["expiration"].apply(lambda e: (e - today).days if isinstance(e, date) else 0)

    # Deduplicate to one row per (symbol, strike, expiration, put_call, bucket)
    feature_df = df.drop_duplicates(subset=["symbol", "strike", "expiration", "put_call", "bucket"])

    # Write to options_features
    insert_sql = """
        INSERT INTO options_features (
            ts_event, symbol, strike, expiration, put_call,
            rvol, vol_oi_ratio, premium_flow, sweep_intensity, aggressor_ratio,
            delta_exposure, iv_rank, days_to_exp, label_24h
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    rows_out = [
        (
            row["bucket"], row["symbol"], row["strike"], row["expiration"], row["put_call"],
            float(row.get("rvol", 0) or 0),
            float(row.get("vol_oi_ratio", 0) or 0),
            float(row.get("premium_flow", 0) or 0),
            float(row.get("sweep_intensity", 0) or 0),
            float(row.get("aggressor_ratio", 0) or 0),
            float(row.get("delta_exposure", 0) or 0),
            float(row.get("iv_rank", 0) or 0),
            int(row.get("days_to_exp", 0) or 0),
            None,  # label_24h filled in by label generation step
        )
        for _, row in feature_df.iterrows()
    ]

    cur.executemany(insert_sql, rows_out)
    conn.commit()
    count = len(rows_out)
    cur.close()
    conn.close()
    return count
