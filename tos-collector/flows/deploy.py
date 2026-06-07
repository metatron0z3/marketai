"""
Prefect Deployment Registration — run this once after the API key is live.

Registers all TOS collector flows with the shared Prefect server (port 4200).
After running this script, flows appear in the Prefect UI and run on schedule.

Usage:
    python -m flows.deploy                     # register all flows
    python -m flows.deploy --flow backfill     # register only backfill
    python -m flows.deploy --run-backfill      # register + immediately run backfill

Prerequisites:
    PREFECT_API_URL=http://localhost:4200/api  (or your Prefect cloud URL)
    SCHWAB_API_KEY, SCHWAB_APP_SECRET set in environment
"""
import argparse
import asyncio
import logging
import os

from prefect.client.orchestration import get_client
from prefect.deployments import Deployment
from prefect.server.schemas.schedules import CronSchedule, IntervalSchedule
from datetime import timedelta

from flows.eod_processing import (
    baseline_refresh_flow,
    earnings_refresh_flow,
    eod_label_flow,
    nightly_orchestration_flow,
)
from flows.historical_backfill import historical_backfill_flow
from flows.intraday_collection import intraday_collection_flow

log = logging.getLogger(__name__)

PREFECT_API = os.getenv("PREFECT_API_URL", "http://localhost:4200/api")
WORK_POOL   = os.getenv("PREFECT_WORK_POOL", "default")


DEPLOYMENTS = [
    # ------------------------------------------------------------------
    # ONE-TIME (manually triggered after API key is live)
    # ------------------------------------------------------------------
    {
        "name":        "backfill",
        "flow":        historical_backfill_flow,
        "description": "One-time historical data backfill — trigger manually",
        "schedule":    None,   # no schedule; run manually
        "parameters":  {"days": 90},
        "tags":        ["tos", "backfill"],
    },

    # ------------------------------------------------------------------
    # INTRADAY — every 5 minutes, market hours
    # M-F 09:30–16:00 ET = cron every 5 min filtered by market_hours check in flow
    # ------------------------------------------------------------------
    {
        "name":        "intraday-5min",
        "flow":        intraday_collection_flow,
        "description": "Chain snapshots + unusual volume detection every 5 minutes",
        "schedule":    IntervalSchedule(interval=timedelta(minutes=5)),
        "parameters":  {},
        "tags":        ["tos", "intraday"],
    },

    # ------------------------------------------------------------------
    # EOD — 4:30 PM ET daily (market days)
    # ------------------------------------------------------------------
    {
        "name":        "eod-labels",
        "flow":        eod_label_flow,
        "description": "Fill T+1/T+5 follow-through labels after market close",
        "schedule":    CronSchedule(cron="30 20 * * 1-5", timezone="UTC"),  # 4:30 PM ET
        "parameters":  {},
        "tags":        ["tos", "eod"],
    },

    # ------------------------------------------------------------------
    # NIGHTLY ORCHESTRATION — 22:00 ET (triggers MarketAI retrain)
    # ------------------------------------------------------------------
    {
        "name":        "nightly",
        "flow":        nightly_orchestration_flow,
        "description": "Check new data volume, trigger MarketAI retrain if threshold met",
        "schedule":    CronSchedule(cron="0 3 * * 2-6", timezone="UTC"),   # 10 PM ET
        "parameters":  {},
        "tags":        ["tos", "nightly"],
    },

    # ------------------------------------------------------------------
    # WEEKLY — Sunday 20:00 ET
    # ------------------------------------------------------------------
    {
        "name":        "weekly-baselines",
        "flow":        baseline_refresh_flow,
        "description": "Recompute rolling 20d volume baselines",
        "schedule":    CronSchedule(cron="0 0 * * 1", timezone="UTC"),     # Sunday 8 PM ET
        "parameters":  {},
        "tags":        ["tos", "weekly"],
    },
    {
        "name":        "weekly-earnings",
        "flow":        earnings_refresh_flow,
        "description": "Refresh earnings calendar for next 4 weeks",
        "schedule":    CronSchedule(cron="30 0 * * 1", timezone="UTC"),    # Sunday 8:30 PM ET
        "parameters":  {},
        "tags":        ["tos", "weekly"],
    },
]


async def register_all(flows_filter: str | None = None) -> None:
    targets = DEPLOYMENTS
    if flows_filter:
        targets = [d for d in DEPLOYMENTS if flows_filter in d["name"]]
        if not targets:
            raise ValueError(f"No deployment matching '{flows_filter}'")

    for d in targets:
        deployment = await Deployment.build_from_flow(
            flow=d["flow"],
            name=d["name"],
            work_pool_name=WORK_POOL,
            schedules=[d["schedule"]] if d["schedule"] else [],
            parameters=d.get("parameters", {}),
            tags=d.get("tags", []),
            description=d["description"],
        )
        deployment_id = await deployment.apply()
        log.info("Registered: %s/%s (id=%s)", d["flow"].name, d["name"], deployment_id)
        print(f"✓ {d['flow'].name}/{d['name']}")


async def run_backfill_now() -> None:
    from prefect.deployments import run_deployment
    print("Triggering backfill flow run...")
    fr = await run_deployment(
        name="tos_historical_backfill/backfill",
        parameters={"days": 90},
        timeout=0,
    )
    print(f"Backfill started: {fr.id}")
    print(f"Monitor at: {PREFECT_API.replace('/api', '')}/flow-runs/{fr.id}")


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Register TOS collector Prefect deployments")
    parser.add_argument("--flow",         default=None, help="Filter to specific flow name")
    parser.add_argument("--run-backfill", action="store_true",
                        help="Also trigger backfill immediately after registering")
    args = parser.parse_args()

    print(f"\nPrefect API: {PREFECT_API}")
    print(f"Work pool:   {WORK_POOL}\n")

    asyncio.run(register_all(args.flow))
    print("\nAll deployments registered.")
    print(f"View in Prefect UI: {PREFECT_API.replace('/api', '')}\n")

    if args.run_backfill:
        asyncio.run(run_backfill_now())


if __name__ == "__main__":
    main()
