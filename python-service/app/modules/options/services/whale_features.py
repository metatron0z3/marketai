from datetime import date, timedelta

import pandas as pd

from app.core.db import get_db_connection


def _today() -> date:
    return date.today()


def compute_whale_features(
    symbol: str,
    start_date: str,
    end_date: str,
    data_source: str = "databento",
) -> int:
    """
    Filter options activity for whale-qualifying trades and compute daily cluster features.

    data_source: "databento" reads from options_trades (default, Databento/OPRA path).
                 "massive"   reads from options_bars (Massive REST path).

    Databento filter criteria (applied before aggregation):
    - aggressor_side = 'BUY'
    - days_to_exp BETWEEN 14 AND 60
    - premium >= 25,000

    Massive filter criteria (bar-derived proxies):
    - premium proxy = close * volume * 100 >= 25,000
    - days_to_exp BETWEEN 14 AND 60
    - aggressor_side and is_sweep not available; cluster features that depend on them are zero-filled.

    Results are written to whale_trades and whale_features.
    """
    conn = get_db_connection()
    cur = conn.cursor()

    if data_source == "massive":
        cur.execute(
            """
            SELECT ts_event, underlying_symbol AS symbol, strike_price AS strike,
                   expiration_date AS expiration, contract_type AS put_call,
                   close, volume, transactions
            FROM options_bars
            WHERE underlying_symbol = %s
              AND ts_event >= %s
              AND ts_event <= %s
            ORDER BY ts_event
            """,
            (symbol, start_date, end_date),
        )
    else:
        cur.execute(
            """
            SELECT ts_event, symbol, strike, expiration, put_call,
                   price, size, premium, delta, iv, open_interest
            FROM options_trades
            WHERE symbol = %s
              AND ts_event >= %s
              AND ts_event <= %s
              AND aggressor_side = 'BUY'
              AND premium >= 25000
            ORDER BY ts_event
            """,
            (symbol, start_date, end_date),
        )

    rows = cur.fetchall()

    if not rows:
        cur.close()
        conn.close()
        return 0

    today = _today()

    if data_source == "massive":
        cols = [
            "ts_event", "symbol", "strike", "expiration", "put_call",
            "close", "volume", "transactions",
        ]
        df = pd.DataFrame(rows, columns=cols)
        df["ts_event"] = pd.to_datetime(df["ts_event"])
        df["date"] = df["ts_event"].dt.date

        # Derive premium proxy and apply whale filter
        df["premium"] = df["close"] * df["volume"] * 100
        df = df[df["premium"] >= 25000].copy()

        df["days_to_exp"] = df["expiration"].apply(
            lambda e: (e - today).days if isinstance(e, date) else 0
        )
        df = df[(df["days_to_exp"] >= 14) & (df["days_to_exp"] <= 60)].copy()

        if df.empty:
            cur.close()
            conn.close()
            return 0

        # Enrich with underlying equity close for otm_pct via underlying_bars
        try:
            window_end = (pd.to_datetime(end_date) + timedelta(days=1)).isoformat()
            cur.execute(
                """
                SELECT ts_event, close AS eq_price
                FROM underlying_bars
                WHERE symbol = %s
                  AND ts_event >= %s
                  AND ts_event <= %s
                ORDER BY ts_event
                """,
                (symbol, start_date, window_end),
            )
            equity_rows = cur.fetchall()
            if equity_rows:
                eq_df = pd.DataFrame(equity_rows, columns=["ts_event", "eq_price"])
                eq_df["ts_event"] = pd.to_datetime(eq_df["ts_event"], utc=True)
                df_sorted = df.sort_values("ts_event")
                eq_sorted = eq_df.sort_values("ts_event")
                if df_sorted["ts_event"].dt.tz is None:
                    eq_sorted["ts_event"] = eq_sorted["ts_event"].dt.tz_localize(None)
                merged = pd.merge_asof(df_sorted, eq_sorted, on="ts_event", direction="backward")
                df["eq_price"] = merged["eq_price"].values
                df["otm_pct"] = (df["strike"] - df["eq_price"]) / df["eq_price"].replace(0, 1)
            else:
                df["otm_pct"] = 0.0
        except Exception:
            df["otm_pct"] = 0.0

        # Bar-derived zero proxies for tick-level fields
        df["price"] = df["close"]
        df["size"] = df["volume"]
        df["delta"] = 0.0
        df["iv"] = 0.0
        df["open_interest"] = 0

    else:
        cols = [
            "ts_event", "symbol", "strike", "expiration", "put_call",
            "price", "size", "premium", "delta", "iv", "open_interest",
        ]
        df = pd.DataFrame(rows, columns=cols)
        df["ts_event"] = pd.to_datetime(df["ts_event"])
        df["date"] = df["ts_event"].dt.date

        df["days_to_exp"] = df["expiration"].apply(
            lambda e: (e - today).days if isinstance(e, date) else 0
        )
        df = df[(df["days_to_exp"] >= 14) & (df["days_to_exp"] <= 60)].copy()

        if df.empty:
            cur.close()
            conn.close()
            return 0

        # Enrich with underlying equity price for otm_pct via trades_data
        try:
            window_end = (pd.to_datetime(end_date) + timedelta(days=1)).isoformat()
            cur.execute(
                """
                SELECT ts_event, price
                FROM trades_data
                WHERE symbol = %s
                  AND ts_event >= %s
                  AND ts_event <= %s
                ORDER BY ts_event
                """,
                (symbol, start_date, window_end),
            )
            equity_rows = cur.fetchall()
            if equity_rows:
                eq_df = pd.DataFrame(equity_rows, columns=["ts_event", "eq_price"])
                eq_df["ts_event"] = pd.to_datetime(eq_df["ts_event"], utc=True)
                df_sorted = df.sort_values("ts_event")
                eq_sorted = eq_df.sort_values("ts_event")
                if df_sorted["ts_event"].dt.tz is None:
                    eq_sorted["ts_event"] = eq_sorted["ts_event"].dt.tz_localize(None)
                merged = pd.merge_asof(df_sorted, eq_sorted, on="ts_event", direction="backward")
                df["eq_price"] = merged["eq_price"].values
                df["otm_pct"] = (df["strike"] - df["eq_price"]) / df["eq_price"].replace(0, 1)
            else:
                df["otm_pct"] = 0.0
        except Exception:
            df["otm_pct"] = 0.0

    # Write whale_trades (individual qualifying trades/bars)
    whale_trade_sql = """
        INSERT INTO whale_trades (
            ts_event, symbol, strike, expiration, put_call,
            price, size, premium, delta, iv, open_interest, days_to_exp, otm_pct
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    whale_trade_rows = [
        (
            row["ts_event"], row["symbol"], row["strike"], row["expiration"], row["put_call"],
            float(row["price"] or 0), int(row["size"] or 0), float(row["premium"] or 0),
            float(row["delta"] or 0), float(row["iv"] or 0), int(row["open_interest"] or 0),
            int(row["days_to_exp"] or 0), float(row.get("otm_pct", 0) or 0),
        )
        for _, row in df.iterrows()
    ]
    cur.executemany(whale_trade_sql, whale_trade_rows)
    conn.commit()

    # Daily cluster aggregation
    cluster_keys = ["symbol", "strike", "expiration", "put_call", "date"]

    if data_source == "massive":
        # Use transactions as cluster_trade_count proxy; vol_oi_ratio and iv_rank unavailable
        clusters = df.groupby(cluster_keys).agg(
            cluster_premium_total=("premium", "sum"),
            cluster_size_max=("size", "max"),
            cluster_trade_count=("transactions", "sum"),
            avg_dte=("days_to_exp", "mean"),
            otm_pct=("otm_pct", "mean"),
            total_size=("size", "sum"),
        ).reset_index()
        clusters["avg_delta"] = 0.0
        clusters["vol_oi_ratio"] = 0.0
        clusters["iv_rank"] = 0.0
    else:
        clusters = df.groupby(cluster_keys).agg(
            cluster_premium_total=("premium", "sum"),
            cluster_size_max=("size", "max"),
            cluster_trade_count=("premium", "count"),
            avg_dte=("days_to_exp", "mean"),
            avg_delta=("delta", "mean"),
            avg_iv=("iv", "mean"),
            otm_pct=("otm_pct", "mean"),
            total_size=("size", "sum"),
            max_oi=("open_interest", "max"),
        ).reset_index()

        clusters["vol_oi_ratio"] = clusters["total_size"] / clusters["max_oi"].replace(0, 1)

        iv_range_stats = (
            df.groupby(["symbol", "strike", "expiration", "put_call"])["iv"]
            .agg(iv_low="min", iv_high="max")
            .reset_index()
        )
        clusters = clusters.merge(
            iv_range_stats, on=["symbol", "strike", "expiration", "put_call"], how="left"
        )
        iv_range = (clusters["iv_high"] - clusters["iv_low"]).replace(0, 1)
        clusters["iv_rank"] = ((clusters["avg_iv"] - clusters["iv_low"]) / iv_range).fillna(0).clip(0, 1)

    clusters["premium_per_trade"] = (
        clusters["cluster_premium_total"] / clusters["cluster_trade_count"].replace(0, 1)
    )
    clusters["avg_dte"] = clusters["avg_dte"].round().astype(int)

    # strike_concentration: 1 - std(strikes) / mean(strikes) per (symbol, day)
    strike_stats = (
        df.groupby(["symbol", "date"])["strike"]
        .agg(strike_std="std", strike_mean="mean")
        .reset_index()
    )
    strike_stats["strike_concentration"] = (
        1 - strike_stats["strike_std"] / strike_stats["strike_mean"].replace(0, 1)
    ).fillna(1.0).clip(0, 1)
    clusters = clusters.merge(
        strike_stats[["symbol", "date", "strike_concentration"]],
        on=["symbol", "date"],
        how="left",
    )

    # call_put_ratio: call premium / total premium per (symbol, day)
    cp = (
        df.groupby(["symbol", "date", "put_call"])["premium"]
        .sum()
        .unstack(fill_value=0)
        .reset_index()
    )
    if "C" not in cp.columns:
        cp["C"] = 0.0
    if "P" not in cp.columns:
        cp["P"] = 0.0
    cp["call_put_ratio"] = cp["C"] / (cp["C"] + cp["P"]).replace(0, 1)
    clusters = clusters.merge(cp[["symbol", "date", "call_put_ratio"]], on=["symbol", "date"], how="left")

    # accumulation_days: distinct qualifying trading days in past 5 calendar days per contract
    contract_dates = (
        df.groupby(["symbol", "strike", "expiration", "put_call"])["date"]
        .apply(set)
        .reset_index()
        .rename(columns={"date": "qualifying_dates"})
    )
    clusters = clusters.merge(
        contract_dates, on=["symbol", "strike", "expiration", "put_call"], how="left"
    )

    def _prior_day_count(row) -> int:
        qdates = row.get("qualifying_dates")
        if not isinstance(qdates, set):
            return 0
        d = row["date"]
        return sum(1 for qd in qdates if 0 < (d - qd).days <= 5)

    clusters["accumulation_days"] = clusters.apply(_prior_day_count, axis=1)

    drop_cols = ["qualifying_dates", "total_size"]
    if data_source != "massive":
        drop_cols += ["avg_iv", "iv_low", "iv_high", "max_oi"]
    clusters = clusters.drop(columns=[c for c in drop_cols if c in clusters.columns])

    # Set ts_event to market open for the trading day
    clusters["ts_event"] = pd.to_datetime(clusters["date"].astype(str) + " 09:30:00")

    insert_sql = """
        INSERT INTO whale_features (
            ts_event, symbol, strike, expiration, put_call,
            cluster_premium_total, cluster_size_max, cluster_trade_count,
            strike_concentration, avg_dte, otm_pct, avg_delta,
            premium_per_trade, vol_oi_ratio, iv_rank,
            accumulation_days, call_put_ratio, label_4w
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    out_rows = [
        (
            row["ts_event"], row["symbol"], row["strike"], row["expiration"], row["put_call"],
            float(row.get("cluster_premium_total", 0) or 0),
            int(row.get("cluster_size_max", 0) or 0),
            int(row.get("cluster_trade_count", 0) or 0),
            float(row.get("strike_concentration", 0) or 0),
            int(row.get("avg_dte", 0) or 0),
            float(row.get("otm_pct", 0) or 0),
            float(row.get("avg_delta", 0) or 0),
            float(row.get("premium_per_trade", 0) or 0),
            float(row.get("vol_oi_ratio", 0) or 0),
            float(row.get("iv_rank", 0) or 0),
            int(row.get("accumulation_days", 0) or 0),
            float(row.get("call_put_ratio", 0) or 0),
            None,
        )
        for _, row in clusters.iterrows()
    ]

    cur.executemany(insert_sql, out_rows)
    conn.commit()
    count = len(out_rows)
    cur.close()
    conn.close()
    return count
