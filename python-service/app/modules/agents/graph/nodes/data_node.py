"""data_node — wraps DataAgent; queries QuestDB and builds feature batches."""
from __future__ import annotations

import logging

from app.modules.agents.graph.state import GraphState

log = logging.getLogger(__name__)


def data_node(state: GraphState) -> dict:
    from app.modules.agents.base_agent import AgentContext
    from app.modules.agents.data_agent import DataAgent

    ctx = AgentContext(
        run_id="",
        target_date=state["target_date"],
        symbols=state["symbols"],
        budget_remaining_usd=state.get("budget_daily_cap", 0) - state.get("budget_daily_spent", 0),
    )

    agent   = DataAgent()
    batches: list[dict] = []
    total   = 0
    errors: list[str] = []

    for symbol in state["symbols"]:
        try:
            result = agent.run(ctx, symbol=symbol)
            if result.get("batch"):
                # SignalBatch is a dataclass — store as plain dict for state transport
                b = result["batch"]
                batches.append({
                    "symbol":     b.symbol,
                    "date":       b.date,
                    "signals":    b.signals,
                    "clusters":   b.clusters,
                    "ranked_ids": b.ranked_ids,
                })
                total += result["count"]
        except Exception as exc:
            msg = f"data_node {symbol}: {exc}"
            log.warning(msg)
            errors.append(msg)

    log.info("data_node: %d batches, %d total signals", len(batches), total)
    return {
        "signal_batches": batches,
        "total_signals":  total,
        "errors":         errors,
    }
