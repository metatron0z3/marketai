import os
import requests


def create_options_tables() -> None:
    host = os.getenv("QUESTDB_HOST", "questdb")
    base_url = f"http://{host}:9000"

    tables = [
        """
        CREATE TABLE IF NOT EXISTS options_trades (
            ts_event TIMESTAMP,
            symbol SYMBOL,
            strike DOUBLE,
            expiration DATE,
            put_call SYMBOL,
            price DOUBLE,
            size LONG,
            bid DOUBLE,
            ask DOUBLE,
            trade_condition SYMBOL,
            exchange SYMBOL,
            iv DOUBLE,
            delta DOUBLE,
            gamma DOUBLE,
            vega DOUBLE,
            theta DOUBLE,
            open_interest LONG,
            aggressor_side SYMBOL,
            is_sweep BOOLEAN,
            premium DOUBLE
        ) TIMESTAMP(ts_event) PARTITION BY DAY;
        """,
        """
        CREATE TABLE IF NOT EXISTS options_features (
            ts_event TIMESTAMP,
            symbol SYMBOL,
            strike DOUBLE,
            expiration DATE,
            put_call SYMBOL,
            rvol DOUBLE,
            vol_oi_ratio DOUBLE,
            premium_flow DOUBLE,
            sweep_intensity DOUBLE,
            aggressor_ratio DOUBLE,
            delta_exposure DOUBLE,
            iv_rank DOUBLE,
            days_to_exp INT,
            label_24h INT
        ) TIMESTAMP(ts_event) PARTITION BY DAY;
        """,
    ]

    for ddl in tables:
        resp = requests.get(base_url + "/exec", params={"query": ddl.strip()})
        resp.raise_for_status()
