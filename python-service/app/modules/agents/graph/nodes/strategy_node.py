"""
strategy_node — 1 LLM call per flagged signal (fan-out via Send).

Each invocation receives a per-signal slice from route_to_strategy().
Results accumulate in state["trade_params"] via the operator.add reducer.
"""
from __future__ import annotations

import logging
import math

from app.modules.agents.graph.models import TradeParams
from app.modules.agents.graph.prompts import build_strategy_prompt
from app.modules.llm.model_factory import get_agent_model

log = logging.getLogger(__name__)

MAX_POSITION_PCT = 5.0      # hard cap regardless of Kelly
HALF_KELLY_FACTOR = 0.5     # standard risk management — never full Kelly


def _compute_kelly(signal: dict) -> float:
    """
    Half-Kelly position fraction.

    win_prob  ≈ cluster_hit_rate
    win_loss  ≈ conviction_score as proxy for edge / risk ratio
    kelly = (p*b - q) / b  →  half_kelly = kelly * 0.5
    """
    p = float(signal.get("cluster_hit_rate", 0.5))
    b = max(float(signal.get("conviction_score", 0.5)) * 3, 1.0)   # crude W/L proxy
    q = 1.0 - p
    kelly = (p * b - q) / b
    kelly = max(0.0, min(kelly, 1.0))
    return round(kelly * HALF_KELLY_FACTOR, 4)


def strategy_node(state: dict) -> dict:
    """
    Receives a per-signal state slice (sent by route_to_strategy).
    Returns {"trade_params": [single_trade_params_dict]} for operator.add accumulation.
    """
    signal       = state["signal"]
    research_ctx = state.get("research_context")
    alias        = state.get("model_alias", "sonnet")
    dry_run      = state.get("dry_run", False)

    if dry_run:
        log.info("strategy_node: dry_run — %s", signal.get("signal_id", "?"))
        return {"trade_params": [{
            "ticker":          signal.get("symbol", "?"),
            "direction":       "CALL",
            "entry_condition": "dry_run",
            "strike_preference": "ATM",
            "dte_target":      "30",
            "position_sizing": {"kelly_fraction": 0.0, "recommended_pct": "0%", "max_contracts": 0},
            "stop_loss":       "dry_run",
            "profit_target":   "dry_run",
            "hedges":          "none",
            "rationale":       "dry_run",
            "conviction_score": float(signal.get("conviction_score", 0)),
            "signal_id":       signal.get("signal_id", ""),
        }]}

    kelly    = _compute_kelly(signal)
    messages = build_strategy_prompt(signal, research_ctx, kelly)

    llm = get_agent_model("strategy", override=alias)
    try:
        result: TradeParams = llm.with_structured_output(TradeParams).invoke(messages)
        log.info("strategy_node: %s %s — kelly=%.3f", result.ticker, result.direction, kelly)
        return {"trade_params": [result.model_dump()]}
    except Exception as exc:
        log.error("strategy_node LLM call failed for %s: %s", signal.get("signal_id"), exc)
        return {
            "trade_params": [],
            "errors": [f"strategy_node {signal.get('signal_id', '?')}: {exc}"],
        }
