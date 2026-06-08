"""
GraphState — the single TypedDict that flows through every node of the analysis graph.

Each node reads from state and returns a partial dict; LangGraph merges it in.
trade_params uses operator.add so parallel Send() executions accumulate results
rather than overwriting each other.
"""
from __future__ import annotations

import operator
from typing import Annotated
from typing_extensions import TypedDict


class GraphState(TypedDict):
    # ── Inputs (set once by the caller) ──────────────────────────────────
    target_date:   str
    symbols:       list[str]
    model_aliases: dict[str, str]        # e.g. {"research": "deepseek-chat"}
    dry_run:       bool

    # ── Budget (set by budget_check, decremented by LLM nodes) ───────────
    budget_daily_cap:       float
    budget_daily_spent:     float
    budget_monthly_cap:     float
    budget_monthly_spent:   float
    budget_ok:              bool          # False → graph routes to end_early

    # ── Data layer (data_node output) ────────────────────────────────────
    signal_batches:    list[dict]         # one SignalBatch-dict per symbol
    total_signals:     int

    # ── ML layer (ml_node output) ────────────────────────────────────────
    scored_batches:    list[dict]         # one ScoredBatch-dict per symbol
    flagged_signals:   list[dict]         # signals above conviction threshold
    total_flagged:     int

    # ── Research layer (research_node output) ────────────────────────────
    research_context:  dict | None

    # ── Strategy layer (strategy_node output — accumulates via Send fan-out)
    trade_params:      Annotated[list[dict], operator.add]

    # ── Synthesis layer (synthesis_node output) ──────────────────────────
    daily_brief:       dict | None

    # ── Errors / warnings accumulated across nodes ───────────────────────
    errors:            list[str]
