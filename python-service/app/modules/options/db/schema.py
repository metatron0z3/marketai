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


def create_massive_tables() -> None:
    """
    Create QuestDB tables for the Massive REST ingest path.

    options_contracts  — contract reference metadata from /v3/reference/options/contracts
    options_bars       — option OHLCV aggregate bars from /v2/aggs (NOT raw tick trades)
    underlying_bars    — stock OHLCV aggregate bars used for labeling and otm_pct enrichment
    options_ingest_runs — one row per ingest job with counters and final status

    options_trades is left unchanged; it is reserved for raw tick trades (Databento/OPRA).
    Aggregate bars from Massive are never inserted into options_trades.
    """
    host = os.getenv("QUESTDB_HOST", "questdb")
    base_url = f"http://{host}:9000"

    tables = [
        """
        CREATE TABLE IF NOT EXISTS options_contracts (
            massive_ticker    SYMBOL,
            underlying_symbol SYMBOL,
            contract_type     SYMBOL,
            expiration_date   DATE,
            strike_price      DOUBLE,
            shares_per_contract DOUBLE,
            exercise_style    SYMBOL,
            primary_exchange  SYMBOL,
            active            BOOLEAN,
            as_of             DATE,
            fetched_at        TIMESTAMP,
            source            SYMBOL
        ) TIMESTAMP(fetched_at) PARTITION BY DAY;
        """,
        """
        CREATE TABLE IF NOT EXISTS options_bars (
            ts_event          TIMESTAMP,
            massive_ticker    SYMBOL,
            underlying_symbol SYMBOL,
            expiration_date   DATE,
            strike_price      DOUBLE,
            contract_type     SYMBOL,
            bar_multiplier    INT,
            bar_timespan      SYMBOL,
            open              DOUBLE,
            high              DOUBLE,
            low               DOUBLE,
            close             DOUBLE,
            volume            LONG,
            transactions      LONG,
            vwap              DOUBLE,
            source            SYMBOL,
            ingest_run_id     STRING
        ) TIMESTAMP(ts_event) PARTITION BY DAY;
        """,
        """
        CREATE TABLE IF NOT EXISTS underlying_bars (
            ts_event       TIMESTAMP,
            symbol         SYMBOL,
            bar_multiplier INT,
            bar_timespan   SYMBOL,
            open           DOUBLE,
            high           DOUBLE,
            low            DOUBLE,
            close          DOUBLE,
            volume         LONG,
            transactions   LONG,
            vwap           DOUBLE,
            source         SYMBOL,
            ingest_run_id  STRING
        ) TIMESTAMP(ts_event) PARTITION BY DAY;
        """,
        """
        CREATE TABLE IF NOT EXISTS options_ingest_runs (
            ts_started              TIMESTAMP,
            ingest_run_id           STRING,
            source                  SYMBOL,
            underlying_symbol       SYMBOL,
            start_date              DATE,
            end_date                DATE,
            requested_resolution    STRING,
            contracts_discovered    LONG,
            contracts_ingested      LONG,
            bars_written            LONG,
            underlying_bars_written LONG,
            status                  SYMBOL,
            error                   STRING,
            ts_finished             TIMESTAMP
        ) TIMESTAMP(ts_started) PARTITION BY DAY;
        """,
    ]

    for ddl in tables:
        resp = requests.get(base_url + "/exec", params={"query": ddl.strip()})
        resp.raise_for_status()


def create_whale_tables() -> None:
    host = os.getenv("QUESTDB_HOST", "questdb")
    base_url = f"http://{host}:9000"

    tables = [
        """
        CREATE TABLE IF NOT EXISTS whale_trades (
            ts_event      TIMESTAMP,
            symbol        SYMBOL,
            strike        DOUBLE,
            expiration    DATE,
            put_call      SYMBOL,
            price         DOUBLE,
            size          LONG,
            premium       DOUBLE,
            delta         DOUBLE,
            iv            DOUBLE,
            open_interest LONG,
            days_to_exp   INT,
            otm_pct       DOUBLE
        ) TIMESTAMP(ts_event) PARTITION BY DAY;
        """,
        """
        CREATE TABLE IF NOT EXISTS whale_features (
            ts_event              TIMESTAMP,
            symbol                SYMBOL,
            strike                DOUBLE,
            expiration            DATE,
            put_call              SYMBOL,
            cluster_premium_total DOUBLE,
            cluster_size_max      LONG,
            cluster_trade_count   INT,
            strike_concentration  DOUBLE,
            avg_dte               INT,
            otm_pct               DOUBLE,
            avg_delta             DOUBLE,
            premium_per_trade     DOUBLE,
            vol_oi_ratio          DOUBLE,
            iv_rank               DOUBLE,
            accumulation_days     INT,
            call_put_ratio        DOUBLE,
            label_4w              INT
        ) TIMESTAMP(ts_event) PARTITION BY DAY;
        """,
    ]

    for ddl in tables:
        resp = requests.get(base_url + "/exec", params={"query": ddl.strip()})
        resp.raise_for_status()
