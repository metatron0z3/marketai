"""
Prefect flow — Multi-Agent Options Analysis (LangGraph)

Schedule: 22:45 ET daily (after feature computation at 22:30).
On-demand: POST /api/v1/agents/analyze

The old sequential agent flow (22:30 ET, enrichment_flow.py) keeps running in
parallel until this LangGraph flow is validated in production. No flag day.

Pipeline (all in one graph.invoke() call):
  budget_check → data_node → ml_node
    ├── no signals → synthesis_node → persist_node
    └── has signals → research_node → strategy_node×N → synthesis_node → persist_node

LangSmith traces every node automatically when LANGCHAIN_TRACING_V2=true.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

from prefect import flow, get_run_logger, task

log = logging.getLogger(__name__)

WATCHLIST = [
    "TSLA", "NVDA", "SPY", "QQQ", "AAPL", "AMD",
    "META", "AMZN", "MSFT", "PLTR", "GLD", "TLT",
]


@task(name="run_analysis_graph", retries=1, retry_delay_seconds=120)
def run_analysis_graph_task(
    target_date: str,
    symbols: list[str],
    model_aliases: dict,
    dry_run: bool,
) -> dict:
    from langchain_core.runnables import RunnableConfig
    from app.modules.agents.graph.analysis_graph import build_analysis_graph, make_initial_state
    from app.modules.llm.qdb_callback import QDBCostCallback

    logger = get_run_logger()
    logger.info(
        "analysis_graph: %d symbols for %s (dry_run=%s, aliases=%s)",
        len(symbols), target_date, dry_run, model_aliases,
    )

    graph = build_analysis_graph()
    state = make_initial_state(
        target_date=target_date,
        symbols=symbols,
        model_aliases=model_aliases,
        dry_run=dry_run,
    )
    config = RunnableConfig(
        callbacks=[QDBCostCallback(agent_name="analysis_graph")],
    )

    result = graph.invoke(state, config=config)

    flagged = result.get("total_flagged", 0)
    errors  = result.get("errors", [])
    brief   = result.get("daily_brief") or {}
    logger.info(
        "analysis_graph complete: flagged=%d brief=%r errors=%d",
        flagged,
        (brief.get("daily_narrative", "")[:80] if brief else ""),
        len(errors),
    )
    for err in errors:
        logger.warning("graph error: %s", err)

    return result


@flow(
    name="multi_agent_options_analysis_langgraph",
    description="LangGraph multi-agent pipeline: budget→data→ml→research→strategy→synthesis",
    log_prints=True,
)
def multi_agent_analysis_flow(
    symbols: list[str] | None = None,
    target_date: str | None = None,
    model_aliases: dict | None = None,
    dry_run: bool = False,
) -> dict:
    d       = target_date or str(date.today() - timedelta(days=1))
    syms    = symbols or WATCHLIST
    aliases = model_aliases or {}

    result = run_analysis_graph_task(
        target_date=d,
        symbols=syms,
        model_aliases=aliases,
        dry_run=dry_run,
    )

    return {
        "date":         d,
        "symbols":      syms,
        "flagged":      result.get("total_flagged", 0),
        "trade_params": result.get("trade_params", []),
        "brief":        result.get("daily_brief"),
        "errors":       result.get("errors", []),
    }


if __name__ == "__main__":
    multi_agent_analysis_flow()
