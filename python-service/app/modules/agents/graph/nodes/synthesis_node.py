"""synthesis_node — 1 LLM call per run; produces the nightly DailyBrief."""
from __future__ import annotations

import logging
from datetime import date

from app.modules.agents.graph.models import DailyBrief
from app.modules.agents.graph.prompts import build_synthesis_prompt
from app.modules.agents.graph.state import GraphState
from app.modules.llm.model_factory import get_agent_model

log = logging.getLogger(__name__)


def _empty_brief(target_date: str) -> dict:
    return {
        "regime_summary":  "All quiet — no signals above conviction threshold.",
        "top_3_setups":    [],
        "macro_risk_flags": [],
        "sector_rotation": "neutral",
        "daily_narrative": f"No unusual-volume options activity flagged for {target_date}.",
    }


def synthesis_node(state: GraphState) -> dict:
    trade_params = state.get("trade_params") or []

    if not trade_params:
        log.info("synthesis_node: no trade params — writing empty brief")
        return {"daily_brief": _empty_brief(state.get("target_date", str(date.today())))}

    if state.get("dry_run"):
        log.info("synthesis_node: dry_run — skipping LLM call")
        return {"daily_brief": _empty_brief(state.get("target_date", str(date.today())))}

    alias    = state.get("model_aliases", {}).get("synthesis", "sonnet")
    messages = build_synthesis_prompt(
        state["target_date"],
        trade_params,
        state.get("research_context"),
    )

    llm = get_agent_model("synthesis", override=alias)
    try:
        result: DailyBrief = llm.with_structured_output(DailyBrief).invoke(messages)
        log.info("synthesis_node: regime=%r, %d setups", result.regime_summary[:50], len(result.top_3_setups))
        return {"daily_brief": result.model_dump()}
    except Exception as exc:
        log.error("synthesis_node LLM call failed: %s", exc)
        return {
            "daily_brief": _empty_brief(state.get("target_date", str(date.today()))),
            "errors": [f"synthesis_node: {exc}"],
        }
