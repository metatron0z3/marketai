"""budget_check_node — reads llm_audit_log via budget_guard, gates the graph."""
from __future__ import annotations

import logging

from app.modules.agents.graph.state import GraphState

log = logging.getLogger(__name__)


def budget_check_node(state: GraphState) -> dict:
    from app.modules.llm.budget_guard import BudgetExceededError, check_budget
    try:
        status = check_budget()
        log.info(
            "Budget OK — daily $%.4f/$%.2f  monthly $%.4f/$%.2f",
            status["daily_spend"], status["daily_cap"],
            status["monthly_spend"], status["monthly_cap"],
        )
        return {
            "budget_daily_cap":     status["daily_cap"],
            "budget_daily_spent":   status["daily_spend"],
            "budget_monthly_cap":   status["monthly_cap"],
            "budget_monthly_spent": status["monthly_spend"],
            "budget_ok":            True,
            "errors":               [],
        }
    except BudgetExceededError as exc:
        log.error("Budget exceeded: %s", exc)
        return {
            "budget_ok": False,
            "errors":    [f"Budget exceeded: {exc}"],
        }
