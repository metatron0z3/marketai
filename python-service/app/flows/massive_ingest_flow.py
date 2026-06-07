"""
massive_ingest_flow.py — Massive API options ingest orchestrated via Prefect

Wraps run_massive_ingest() as Prefect tasks so each quarter/type run is tracked,
retried on failure, and logged in the Prefect UI.

Triggered manually (no fixed schedule — Massive free tier is slow; new quarters
are added by hand when a new expiry window opens).

Example trigger via Prefect UI or CLI:
    prefect deployment run 'massive-options-ingest/manual' \\
        --param 'runs=[{"symbol":"AAPL","start_date":"2025-01-01","end_date":"2025-03-31","contract_type":"call"}]'
"""

import uuid
from typing import Optional

from prefect import flow, task, get_run_logger


# ---------------------------------------------------------------------------
# Task
# ---------------------------------------------------------------------------

@task(
    name="ingest-quarter",
    retries=1,
    retry_delay_seconds=300,   # wait 5min before retrying (respect rate limit reset)
)
def ingest_quarter(
    symbol: str,
    start_date: str,
    end_date: str,
    contract_type: str,
    bar_timespan: str = "day",
    bar_multiplier: int = 1,
) -> dict:
    """
    Run one quarter of Massive options ingest synchronously.

    Calls run_massive_ingest() directly so Prefect tracks the full wall-clock
    duration (each quarter can take 4-8 hours at free-tier rate limits).
    The task is idempotent — existing bars are skipped by the dedup guard in
    write_option_bars().
    """
    logger = get_run_logger()
    from app.modules.options.services.massive_ingest import run_massive_ingest

    run_id = str(uuid.uuid4())
    logger.info(
        "Starting: %s %s %s→%s  run_id=%s",
        symbol, contract_type, start_date, end_date, run_id,
    )

    run_massive_ingest(
        underlying_symbol=symbol,
        start_date=start_date,
        end_date=end_date,
        bar_timespan=bar_timespan,
        bar_multiplier=bar_multiplier,
        include_expired=True,
        max_contracts=None,       # no cap — fetch all contracts in the window
        ingest_run_id=run_id,
        contract_type=contract_type,
    )

    logger.info("Finished: %s %s %s→%s", symbol, contract_type, start_date, end_date)
    return {"symbol": symbol, "start_date": start_date, "end_date": end_date, "contract_type": contract_type}


# ---------------------------------------------------------------------------
# Flow
# ---------------------------------------------------------------------------

@flow(name="massive-options-ingest", log_prints=True)
def massive_options_ingest(
    runs: list[dict],
) -> list[dict]:
    """
    Ingest Massive API options data for a list of (symbol, start_date, end_date, contract_type) runs.

    Runs execute sequentially — parallel execution would immediately exhaust the
    free-plan 5 req/min rate limit.  Each run is idempotent.

    Example payload:
        [
          {"symbol": "AAPL", "start_date": "2025-01-01", "end_date": "2025-03-31", "contract_type": "call"},
          {"symbol": "AAPL", "start_date": "2025-01-01", "end_date": "2025-03-31", "contract_type": "put"},
        ]
    """
    logger = get_run_logger()
    logger.info("Queued %d ingest run(s)", len(runs))
    results = []

    for run in runs:
        result = ingest_quarter(
            symbol=run["symbol"],
            start_date=run["start_date"],
            end_date=run["end_date"],
            contract_type=run["contract_type"],
            bar_timespan=run.get("bar_timespan", "day"),
            bar_multiplier=run.get("bar_multiplier", 1),
        )
        results.append(result)

    logger.info("All %d run(s) complete", len(results))
    return results


if __name__ == "__main__":
    # Example: ingest AAPL Q1 2025 calls locally
    massive_options_ingest(runs=[
        {"symbol": "AAPL", "start_date": "2025-01-01", "end_date": "2025-03-31", "contract_type": "call"},
    ])
