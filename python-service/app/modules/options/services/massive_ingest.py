import os
import time
from datetime import datetime, timedelta, timezone

import requests

from app.core.db import get_db_connection

MASSIVE_BASE_URL = os.getenv("MASSIVE_BASE_URL", "https://api.massive.com")

# Seconds to wait between paginated requests (free-plan rate limit)
_PAGE_DELAY = float(os.getenv("MASSIVE_PAGE_DELAY", "1.0"))
# Max retries on 429 before giving up
_MAX_RETRIES = 5


def _get_api_key() -> str:
    key = os.getenv("MASSIVE_API_KEY", "")
    if not key:
        raise ValueError("MASSIVE_API_KEY environment variable is not set")
    return key


def _do_get(url: str, api_key: str, params: dict | None = None) -> dict:
    """GET with automatic retry on 429, honouring Retry-After when present."""
    for attempt in range(_MAX_RETRIES):
        resp = requests.get(
            url,
            params=params,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30,
        )
        if resp.status_code == 429:
            retry_after = float(resp.headers.get("Retry-After", 60))
            print(f"    [rate-limit] 429 — waiting {retry_after:.0f}s (attempt {attempt + 1}/{_MAX_RETRIES})", flush=True)
            time.sleep(retry_after)
            continue
        resp.raise_for_status()
        return resp.json()
    raise RuntimeError(f"Exceeded {_MAX_RETRIES} retries on 429 for {url}")


def _massive_get(path: str, params: dict, api_key: str) -> dict:
    return _do_get(f"{MASSIVE_BASE_URL}{path}", api_key, params=params)


def _massive_get_url(url: str, api_key: str) -> dict:
    return _do_get(url, api_key)


def fetch_contracts(
    underlying_symbol: str,
    as_of_date: str,
    include_expired: bool,
    api_key: str,
) -> list[dict]:
    """Fetch all contracts for an underlying via /v3/reference/options/contracts, following pagination."""
    params = {
        "underlying_ticker": underlying_symbol,
        "as_of": as_of_date,
        "expired": str(include_expired).lower(),
        "limit": 250,
    }
    contracts: list[dict] = []
    data = _massive_get("/v3/reference/options/contracts", params, api_key)
    contracts.extend(data.get("results") or [])

    while data.get("next_url"):
        time.sleep(_PAGE_DELAY)
        data = _massive_get_url(data["next_url"], api_key)
        contracts.extend(data.get("results") or [])

    return contracts


def fetch_agg_bars(
    ticker: str,
    multiplier: int,
    timespan: str,
    from_date: str,
    to_date: str,
    api_key: str,
) -> list[dict]:
    """Fetch OHLCV aggregate bars from /v2/aggs, following pagination."""
    path = f"/v2/aggs/ticker/{ticker}/range/{multiplier}/{timespan}/{from_date}/{to_date}"
    params = {"adjusted": "true", "sort": "asc", "limit": 50000}
    bars: list[dict] = []
    data = _massive_get(path, params, api_key)
    bars.extend(data.get("results") or [])

    while data.get("next_url"):
        time.sleep(_PAGE_DELAY)
        data = _massive_get_url(data["next_url"], api_key)
        bars.extend(data.get("results") or [])

    return bars


def _existing_bar_timestamps_ms(
    conn,
    table: str,
    ticker_col: str,
    ticker: str,
    bar_multiplier: int,
    bar_timespan: str,
    start_date: str,
    end_date: str,
) -> set[int]:
    """Return existing bar timestamps as epoch milliseconds for idempotent insert checks."""
    cur = conn.cursor()
    cur.execute(
        f"""
        SELECT ts_event FROM {table}
        WHERE {ticker_col} = %s
          AND bar_multiplier = %s
          AND bar_timespan = %s
          AND ts_event >= %s
          AND ts_event <= %s
        """,
        (ticker, bar_multiplier, bar_timespan, start_date, end_date),
    )
    result: set[int] = set()
    for (ts,) in cur.fetchall():
        if ts is None:
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        result.add(int(ts.timestamp() * 1000))
    cur.close()
    return result


def write_contracts(conn, contracts: list[dict], fetched_at: datetime) -> None:
    if not contracts:
        return
    cur = conn.cursor()
    sql = """
        INSERT INTO options_contracts (
            massive_ticker, underlying_symbol, contract_type, expiration_date,
            strike_price, shares_per_contract, exercise_style, primary_exchange,
            active, as_of, fetched_at, source
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    rows = [
        (
            c.get("ticker"),
            c.get("underlying_ticker"),
            c.get("contract_type"),
            c.get("expiration_date"),
            float(c.get("strike_price") or 0),
            float(c.get("shares_per_contract") or 100),
            c.get("exercise_style"),
            c.get("primary_exchange"),
            bool(c.get("active", True)),
            c.get("as_of"),
            fetched_at,
            "massive",
        )
        for c in contracts
    ]
    cur.executemany(sql, rows)
    conn.commit()
    cur.close()


def write_option_bars(
    conn,
    bars: list[dict],
    ticker: str,
    underlying_symbol: str,
    expiration_date: str,
    strike_price: float,
    contract_type: str,
    bar_multiplier: int,
    bar_timespan: str,
    ingest_run_id: str,
    existing_ts_ms: set[int],
) -> int:
    """Insert option aggregate bars, skipping timestamps already present (idempotent)."""
    if not bars:
        return 0
    sql = """
        INSERT INTO options_bars (
            ts_event, massive_ticker, underlying_symbol, expiration_date, strike_price,
            contract_type, bar_multiplier, bar_timespan,
            open, high, low, close, volume, transactions, vwap,
            source, ingest_run_id
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    rows = []
    for b in bars:
        t_ms = int(b.get("t") or 0)
        if t_ms in existing_ts_ms:
            continue
        ts = datetime.fromtimestamp(t_ms / 1000, tz=timezone.utc)
        rows.append((
            ts, ticker, underlying_symbol, expiration_date, strike_price,
            contract_type, bar_multiplier, bar_timespan,
            float(b.get("o") or 0),
            float(b.get("h") or 0),
            float(b.get("l") or 0),
            float(b.get("c") or 0),
            int(b.get("v") or 0),
            int(b["n"]) if b.get("n") is not None else None,
            float(b["vw"]) if b.get("vw") is not None else None,
            "massive",
            ingest_run_id,
        ))
    if rows:
        cur = conn.cursor()
        cur.executemany(sql, rows)
        conn.commit()
        cur.close()
    return len(rows)


def write_underlying_bars(
    conn,
    bars: list[dict],
    symbol: str,
    bar_multiplier: int,
    bar_timespan: str,
    ingest_run_id: str,
    existing_ts_ms: set[int],
) -> int:
    """Insert underlying stock aggregate bars, skipping timestamps already present (idempotent)."""
    if not bars:
        return 0
    sql = """
        INSERT INTO underlying_bars (
            ts_event, symbol, bar_multiplier, bar_timespan,
            open, high, low, close, volume, transactions, vwap,
            source, ingest_run_id
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    rows = []
    for b in bars:
        t_ms = int(b.get("t") or 0)
        if t_ms in existing_ts_ms:
            continue
        ts = datetime.fromtimestamp(t_ms / 1000, tz=timezone.utc)
        rows.append((
            ts, symbol, bar_multiplier, bar_timespan,
            float(b.get("o") or 0),
            float(b.get("h") or 0),
            float(b.get("l") or 0),
            float(b.get("c") or 0),
            int(b.get("v") or 0),
            int(b["n"]) if b.get("n") is not None else None,
            float(b["vw"]) if b.get("vw") is not None else None,
            "massive",
            ingest_run_id,
        ))
    if rows:
        cur = conn.cursor()
        cur.executemany(sql, rows)
        conn.commit()
        cur.close()
    return len(rows)


def _write_ingest_run(conn, run: dict) -> None:
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO options_ingest_runs (
            ts_started, ingest_run_id, source, underlying_symbol,
            start_date, end_date, requested_resolution,
            contracts_discovered, contracts_ingested, bars_written, underlying_bars_written,
            status, error, ts_finished
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            run["ts_started"], run["ingest_run_id"], run["source"],
            run["underlying_symbol"], run["start_date"], run["end_date"],
            run["requested_resolution"],
            run.get("contracts_discovered", 0), run.get("contracts_ingested", 0),
            run.get("bars_written", 0), run.get("underlying_bars_written", 0),
            run["status"], run.get("error"), run.get("ts_finished"),
        ),
    )
    conn.commit()
    cur.close()


def run_massive_ingest(
    underlying_symbol: str,
    start_date: str,
    end_date: str,
    bar_timespan: str,
    bar_multiplier: int,
    include_expired: bool,
    max_contracts: int,
    ingest_run_id: str,
) -> None:
    """
    Background worker: discover contracts via Massive reference API, fetch OHLCV
    aggregate bars for each contract and the underlying stock, and write to QuestDB.

    Bars are NOT inserted into options_trades — that table is reserved for raw tick trades
    (Databento/OPRA path only). Aggregate bars from Massive go into options_bars and
    underlying_bars.

    The underlying bar window is extended 30 days past end_date so that label generation
    can join future prices from underlying_bars without a separate ingest.

    NOTE — downstream feature code:
    services/features.py computes aggressor_ratio, sweep_intensity, vol_oi_ratio, and
    iv_rank from options_trades columns (bid, ask, exchange, open_interest, iv). None of
    those fields exist in options_bars (Massive free plan does not provide tick trades,
    quotes, open interest, or Greeks). features.py must be adapted to a bar-volume feature
    strategy (RVOL from volume/avg_volume, premium_flow from close*volume*100, momentum
    from OHLC) before the unusual-volume pipeline can run on Massive-ingested data.

    NOTE — label generation:
    services/labels.py and services/whale_labels.py currently read equity prices from
    trades_data (Databento schema). For Massive-ingested datasets, they must be updated to
    read from underlying_bars (keyed by symbol + ts_event) instead.
    services/whale_features.py similarly reads from trades_data for otm_pct enrichment.
    """
    api_key = _get_api_key()
    ts_started = datetime.now(timezone.utc)
    conn = get_db_connection()

    run: dict = {
        "ts_started": ts_started,
        "ingest_run_id": ingest_run_id,
        "source": "massive",
        "underlying_symbol": underlying_symbol,
        "start_date": start_date,
        "end_date": end_date,
        "requested_resolution": f"{bar_multiplier}/{bar_timespan}",
        "contracts_discovered": 0,
        "contracts_ingested": 0,
        "bars_written": 0,
        "underlying_bars_written": 0,
        "status": "running",
        "error": None,
        "ts_finished": None,
    }

    try:
        # Step 1: Discover and store contract metadata
        contracts = fetch_contracts(underlying_symbol, end_date, include_expired, api_key)
        contracts = contracts[:max_contracts]
        run["contracts_discovered"] = len(contracts)
        write_contracts(conn, contracts, ts_started)

        # Step 2: Ingest OHLCV bars for each option contract
        total_option_bars = 0
        contracts_ingested = 0

        for contract in contracts:
            ticker = contract.get("ticker") or ""
            if not ticker:
                continue

            existing_ts = _existing_bar_timestamps_ms(
                conn, "options_bars", "massive_ticker",
                ticker, bar_multiplier, bar_timespan, start_date, end_date,
            )

            try:
                bars = fetch_agg_bars(ticker, bar_multiplier, bar_timespan, start_date, end_date, api_key)
            except requests.HTTPError as exc:
                # 404 = no bars for this contract in the requested window; skip without failing
                if exc.response is not None and exc.response.status_code == 404:
                    continue
                raise

            written = write_option_bars(
                conn, bars, ticker,
                underlying_symbol=contract.get("underlying_ticker") or underlying_symbol,
                expiration_date=contract.get("expiration_date") or "",
                strike_price=float(contract.get("strike_price") or 0),
                contract_type=contract.get("contract_type") or "",
                bar_multiplier=bar_multiplier,
                bar_timespan=bar_timespan,
                ingest_run_id=ingest_run_id,
                existing_ts_ms=existing_ts,
            )
            total_option_bars += written
            contracts_ingested += 1

        run["contracts_ingested"] = contracts_ingested
        run["bars_written"] = total_option_bars

        # Step 3: Ingest underlying stock bars (window extended for label generation headroom)
        extended_end = (
            datetime.strptime(end_date, "%Y-%m-%d").date() + timedelta(days=30)
        ).isoformat()

        existing_underlying_ts = _existing_bar_timestamps_ms(
            conn, "underlying_bars", "symbol",
            underlying_symbol, bar_multiplier, bar_timespan, start_date, extended_end,
        )
        underlying_bars = fetch_agg_bars(
            underlying_symbol, bar_multiplier, bar_timespan, start_date, extended_end, api_key
        )
        underlying_written = write_underlying_bars(
            conn, underlying_bars, underlying_symbol,
            bar_multiplier, bar_timespan, ingest_run_id, existing_underlying_ts,
        )
        run["underlying_bars_written"] = underlying_written

        run["status"] = "completed"
        run["ts_finished"] = datetime.now(timezone.utc)

    except Exception as exc:
        run["status"] = "error"
        run["error"] = str(exc)
        run["ts_finished"] = datetime.now(timezone.utc)

    finally:
        _write_ingest_run(conn, run)
        conn.close()
