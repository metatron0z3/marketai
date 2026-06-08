"""
Prefect flow — Multi-Agent Options Analysis

Schedule: 22:45 ET daily (after feature computation at 22:30).
On-demand: POST /api/v1/agents/analyze

Pipeline:
  1. Budget gate
  2. DataAgent per symbol (code only, parallelisable)
  3. MLAgent — scores all signals, flags high conviction
  4. ResearchAgent — one LLM call, cross-symbol context
  5. StrategyAgent — one LLM call per flagged signal (parallelisable)
  6. SynthesisAgent — one LLM call, daily brief
  7. Persist results

Model aliases are resolved from env vars:
  COORDINATOR_MODEL, RESEARCH_MODEL, STRATEGY_MODEL, SYNTHESIS_MODEL
Override per-run via the model_aliases argument.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

from prefect import flow, get_run_logger, task

log = logging.getLogger(__name__)

WATCHLIST = ["TSLA", "NVDA", "SPY", "QQQ", "AAPL", "AMD", "META", "AMZN", "MSFT", "PLTR", "GLD", "TLT"]


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------

@task(name="check_agent_budget", retries=0)
def check_budget_task() -> dict:
    from app.modules.llm.budget_guard import BudgetExceededError, check_budget
    logger = get_run_logger()
    try:
        status = check_budget()
        logger.info(
            "Budget OK — daily $%.4f / $%.2f  monthly $%.4f / $%.2f",
            status["daily_spend"], status["daily_cap"],
            status["monthly_spend"], status["monthly_cap"],
        )
        return status
    except BudgetExceededError as exc:
        logger.error("Budget exceeded — aborting multi-agent flow: %s", exc)
        raise


@task(name="data_agent_task", retries=1, retry_delay_seconds=30)
def data_agent_task(symbol: str, target_date: str, ctx) -> dict:
    from app.modules.agents.data_agent import DataAgent
    logger = get_run_logger()
    agent = DataAgent()
    result = agent.run(ctx, symbol=symbol)
    logger.info("DataAgent %s: %d signals", symbol, result["count"])
    return result


@task(name="ml_agent_task", retries=0)
def ml_agent_task(batch, ctx) -> dict:
    from app.modules.agents.ml_agent import MLAgent
    logger = get_run_logger()
    if batch is None:
        return {"count": 0, "flagged": 0, "scored_batch": None}
    agent = MLAgent()
    result = agent.run(ctx, batch=batch)
    logger.info(
        "MLAgent %s: %d scored, %d flagged",
        result.get("symbol"), result.get("count"), result.get("flagged")
    )
    return result


@task(name="research_agent_task", retries=1, retry_delay_seconds=60)
def research_agent_task(scored_batches: list, ctx, model_alias: str | None = None) -> dict:
    from app.modules.agents.research_agent import ResearchAgent
    logger = get_run_logger()
    agent = ResearchAgent(model_alias=model_alias)
    result = agent.run(ctx, scored_batches=scored_batches)
    theme = result.get("research_context", {}).get("dominant_theme", "")
    logger.info("ResearchAgent: theme=%r", theme)
    return result


@task(name="strategy_agent_task", retries=1, retry_delay_seconds=30)
def strategy_agent_task(signal, research_context: dict, ctx, model_alias: str | None = None) -> dict:
    from app.modules.agents.strategy_agent import StrategyAgent
    logger = get_run_logger()
    agent = StrategyAgent(model_alias=model_alias)
    result = agent.run(ctx, signal=signal, research_context=research_context)
    logger.info(
        "StrategyAgent %s: params generated",
        result.get("trade_params", {}).get("ticker", "?")
    )
    return result


@task(name="synthesis_agent_task", retries=1, retry_delay_seconds=60)
def synthesis_agent_task(
    trade_params_list: list,
    research_context: dict,
    ctx,
    model_alias: str | None = None,
) -> dict:
    from app.modules.agents.synthesis_agent import SynthesisAgent
    logger = get_run_logger()
    agent = SynthesisAgent(model_alias=model_alias)
    result = agent.run(ctx, trade_params_list=trade_params_list, research_context=research_context)
    narrative = result.get("brief", {}).get("daily_narrative", "")[:80]
    logger.info("SynthesisAgent: %r...", narrative)
    return result


# ---------------------------------------------------------------------------
# Flow
# ---------------------------------------------------------------------------

@flow(
    name="multi_agent_options_analysis",
    description="Multi-agent pipeline: data → ML → research → strategy → synthesis",
    log_prints=True,
)
def multi_agent_analysis_flow(
    symbols: list[str] | None = None,
    target_date: str | None = None,
    model_aliases: dict | None = None,
    dry_run: bool = False,
) -> dict:
    logger = get_run_logger()
    d      = target_date or str(date.today() - timedelta(days=1))
    syms   = symbols or WATCHLIST
    aliases = model_aliases or {}

    logger.info(
        "Multi-agent flow: %d symbols for %s (dry_run=%s, aliases=%s)",
        len(syms), d, dry_run, aliases
    )

    # 1. Budget gate
    budget = check_budget_task()

    # Build AgentContext (shared across all agents)
    import uuid
    from app.modules.agents.base_agent import AgentContext
    ctx = AgentContext(
        run_id=str(uuid.uuid4()),
        target_date=d,
        symbols=syms,
        budget_remaining_usd=budget.get("daily_cap", 2.27) - budget.get("daily_spend", 0),
    )

    # 2. DataAgent — parallel per symbol
    data_results = [data_agent_task(sym, d, ctx) for sym in syms]

    # 3. MLAgent — per symbol (code only, fast)
    ml_results = [
        ml_agent_task(r.get("batch"), ctx)
        for r in data_results
    ]

    # Collect all scored batches and flagged signals
    scored_batches = [r.get("scored_batch") for r in ml_results if r.get("scored_batch")]
    all_flagged    = [s for r in ml_results
                      if r.get("scored_batch")
                      for s in r["scored_batch"].flagged]

    logger.info("Total flagged signals: %d", len(all_flagged))

    if not all_flagged or dry_run:
        logger.info("No flagged signals or dry_run — skipping LLM agents")
        return {
            "date": d, "symbols": syms,
            "flagged": 0, "dry_run": dry_run,
            "brief": None, "trade_params": [],
        }

    # 4. ResearchAgent — one call, all symbols merged
    research_result = research_agent_task(
        scored_batches, ctx, model_alias=aliases.get("research")
    )
    research_ctx = research_result.get("research_context", {})

    # 5. StrategyAgent — parallel per flagged signal
    strategy_results = [
        strategy_agent_task(sig, research_ctx, ctx, model_alias=aliases.get("strategy"))
        for sig in all_flagged
    ]

    # 6. SynthesisAgent — one call
    synthesis_result = synthesis_agent_task(
        strategy_results, research_ctx, ctx, model_alias=aliases.get("synthesis")
    )

    return {
        "date":          d,
        "symbols":       syms,
        "flagged":       len(all_flagged),
        "trade_params":  [r.get("trade_params") for r in strategy_results],
        "brief":         synthesis_result.get("brief"),
        "daily_spend":   budget.get("daily_spend", 0),
    }


if __name__ == "__main__":
    multi_agent_analysis_flow()
