#!/usr/bin/env python3
"""
CLI: ingest options + underlying bars from the Massive REST API into QuestDB.

Usage:
    python cli/ingest_massive.py --symbol SPY --start 2025-01-01 --end 2025-03-31

Run from the python-service directory so the app package is on the path:
    cd python-service && python cli/ingest_massive.py --help

Required env vars:
    MASSIVE_API_KEY      Your Massive API key
    QUESTDB_HOST         QuestDB hostname (default: localhost)
"""

import argparse
import os
import sys
import uuid
from datetime import datetime, timezone

# Allow running from repo root or python-service dir
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.db import get_db_connection
from app.modules.options.db.schema import create_massive_tables
from app.modules.options.services.massive_ingest import (
    _write_ingest_run,
    fetch_agg_bars,
    fetch_contracts,
    write_contracts,
    write_option_bars,
    write_underlying_bars,
    _existing_bar_timestamps_ms,
)

import requests
from datetime import timedelta


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Ingest Massive options + underlying bars into QuestDB",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # All calls expiring within Jan-Mar 2025 window
  python cli/ingest_massive.py --symbol TSLA --start 2025-01-01 --end 2025-03-31 --contract-type call

  # All puts for the same window, leave running overnight
  nohup python cli/ingest_massive.py --symbol TSLA --start 2025-01-01 --end 2025-03-31 \\
      --contract-type put > ~/tsla-puts.log 2>&1 &
        """,
    )
    p.add_argument("--symbol", required=True, help="Underlying ticker (e.g. TSLA, SPY)")
    p.add_argument("--start", required=True, metavar="YYYY-MM-DD", help="Bar start date (inclusive)")
    p.add_argument("--end", required=True, metavar="YYYY-MM-DD", help="Bar end date (inclusive)")
    p.add_argument(
        "--contract-type",
        choices=["call", "put"],
        default=None,
        help="Fetch only calls or only puts (default: both)",
    )
    p.add_argument(
        "--timespan",
        default="day",
        choices=["minute", "hour", "day", "week", "month"],
        help="Bar resolution (default: day)",
    )
    p.add_argument("--multiplier", type=int, default=1, help="Bar multiplier (default: 1)")
    p.add_argument(
        "--max-contracts",
        type=int,
        default=None,
        metavar="N",
        help="Cap on contracts to ingest (default: no cap — fetch all)",
    )
    p.add_argument(
        "--no-expired",
        action="store_true",
        help="Exclude expired contracts (default: include expired)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch from API and print counts, but do not write to QuestDB",
    )
    return p.parse_args()


def _log(msg: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def main() -> None:
    args = parse_args()

    api_key = os.getenv("MASSIVE_API_KEY", "")
    if not api_key:
        print("ERROR: MASSIVE_API_KEY is not set", file=sys.stderr)
        sys.exit(1)

    symbol = args.symbol.upper()
    start_date = args.start
    end_date = args.end
    bar_multiplier = args.multiplier
    bar_timespan = args.timespan
    include_expired = not args.no_expired
    max_contracts = args.max_contracts  # None = no cap
    contract_type = args.contract_type
    dry_run = args.dry_run
    ingest_run_id = str(uuid.uuid4())

    _log(f"Massive ingest: {symbol}  {start_date} → {end_date}  "
         f"resolution={bar_multiplier}/{bar_timespan}  "
         f"contract_type={contract_type or 'all'}  "
         f"max_contracts={max_contracts or 'none'}  "
         f"include_expired={include_expired}  "
         f"dry_run={dry_run}")
    _log(f"ingest_run_id: {ingest_run_id}")

    if not dry_run:
        _log("Ensuring QuestDB tables exist...")
        create_massive_tables()

    conn = None if dry_run else get_db_connection()
    ts_started = datetime.now(timezone.utc)

    run: dict = {
        "ts_started": ts_started,
        "ingest_run_id": ingest_run_id,
        "source": "massive",
        "underlying_symbol": symbol,
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
        # Step 1: Contracts
        _log(f"Fetching contracts for {symbol} as_of={end_date} "
             f"expiration>={start_date} contract_type={contract_type or 'all'} ...")
        contracts = fetch_contracts(
            symbol, end_date, include_expired, api_key,
            contract_type=contract_type,
            expiration_date_gte=start_date,
        )
        if max_contracts is not None:
            contracts = contracts[:max_contracts]
        _log(f"  {len(contracts)} contracts discovered")
        run["contracts_discovered"] = len(contracts)

        if not dry_run:
            write_contracts(conn, contracts, ts_started)
            _log("  Contracts written to options_contracts")

        # Step 2: Option bars per contract
        total_option_bars = 0
        contracts_ingested = 0
        skipped = 0

        for i, contract in enumerate(contracts, 1):
            ticker = contract.get("ticker") or ""
            if not ticker:
                continue

            exp = contract.get("expiration_date", "?")
            strike = contract.get("strike_price", "?")
            ctype = contract.get("contract_type", "?")
            label = f"{ticker} ({ctype} {strike} exp {exp})"

            existing_ts: set[int] = set()
            if not dry_run:
                existing_ts = _existing_bar_timestamps_ms(
                    conn, "options_bars", "massive_ticker",
                    ticker, bar_multiplier, bar_timespan, start_date, end_date,
                )

            try:
                bars = fetch_agg_bars(ticker, bar_multiplier, bar_timespan, start_date, end_date, api_key)
            except requests.HTTPError as exc:
                if exc.response is not None and exc.response.status_code == 404:
                    skipped += 1
                    continue
                raise

            if dry_run:
                print(f"  [{i}/{len(contracts)}] {label}: {len(bars)} bars (dry-run, not written)")
                total_option_bars += len(bars)
                contracts_ingested += 1
                continue

            written = write_option_bars(
                conn, bars, ticker,
                underlying_symbol=contract.get("underlying_ticker") or symbol,
                expiration_date=exp,
                strike_price=float(contract.get("strike_price") or 0),
                contract_type=ctype,
                bar_multiplier=bar_multiplier,
                bar_timespan=bar_timespan,
                ingest_run_id=ingest_run_id,
                existing_ts_ms=existing_ts,
            )
            total_option_bars += written
            contracts_ingested += 1
            print(f"  [{i}/{len(contracts)}] {label}: {written} bars written", flush=True)

        run["contracts_ingested"] = contracts_ingested
        run["bars_written"] = total_option_bars
        _log(f"Option bars done: {total_option_bars} bars across {contracts_ingested} contracts "
             f"({skipped} skipped, no data)")

        # Step 3: Underlying bars (window extended 30 days for label generation)
        extended_end = (
            datetime.strptime(end_date, "%Y-%m-%d").date() + timedelta(days=30)
        ).isoformat()

        _log(f"Fetching underlying bars for {symbol} {start_date} → {extended_end} "
             f"(+30d for label headroom)...")

        existing_underlying_ts: set[int] = set()
        if not dry_run:
            existing_underlying_ts = _existing_bar_timestamps_ms(
                conn, "underlying_bars", "symbol",
                symbol, bar_multiplier, bar_timespan, start_date, extended_end,
            )

        underlying_bars = fetch_agg_bars(
            symbol, bar_multiplier, bar_timespan, start_date, extended_end, api_key
        )

        if dry_run:
            _log(f"  {len(underlying_bars)} underlying bars (dry-run, not written)")
            underlying_written = len(underlying_bars)
        else:
            underlying_written = write_underlying_bars(
                conn, underlying_bars, symbol,
                bar_multiplier, bar_timespan, ingest_run_id, existing_underlying_ts,
            )
            _log(f"  {underlying_written} underlying bars written to underlying_bars")

        run["underlying_bars_written"] = underlying_written
        run["status"] = "completed"
        run["ts_finished"] = datetime.now(timezone.utc)

    except Exception as exc:
        run["status"] = "error"
        run["error"] = str(exc)
        run["ts_finished"] = datetime.now(timezone.utc)
        _log(f"ERROR: {exc}")

    finally:
        elapsed = (run["ts_finished"] - ts_started).total_seconds()
        _log(
            f"Done [{run['status']}] in {elapsed:.1f}s — "
            f"contracts={run['contracts_ingested']}/{run['contracts_discovered']}  "
            f"option_bars={run['bars_written']}  "
            f"underlying_bars={run['underlying_bars_written']}"
        )

        if not dry_run and conn:
            _write_ingest_run(conn, run)
            _log(f"Run logged to options_ingest_runs (id={ingest_run_id})")
            conn.close()

        if run["status"] == "error":
            sys.exit(1)


if __name__ == "__main__":
    main()
