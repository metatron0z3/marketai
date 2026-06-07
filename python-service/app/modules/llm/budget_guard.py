"""
Budget guard — queries llm_audit_log to enforce daily and monthly spending limits.

Call check_budget() before any LLM batch to prevent runaway costs.
Raises BudgetExceededError if the configured limit has been hit.
"""
import logging
import os
from datetime import date

log = logging.getLogger(__name__)


class BudgetExceededError(RuntimeError):
    pass


def _query_spend(since_clause: str) -> float:
    """Return total cost_usd from llm_audit_log since a given SQL interval."""
    host = os.getenv("QUESTDB_HOST", "questdb")
    import requests
    sql = f"SELECT sum(cost_usd) FROM llm_audit_log WHERE called_at >= {since_clause}"
    resp = requests.get(
        f"http://{host}:9000/exec",
        params={"query": sql},
        timeout=5,
    )
    resp.raise_for_status()
    data = resp.json()
    try:
        val = data["dataset"][0][0]
        return float(val) if val is not None else 0.0
    except (KeyError, IndexError, TypeError):
        return 0.0


def get_daily_spend() -> float:
    return _query_spend("dateadd('d', -1, now())")


def get_monthly_spend() -> float:
    return _query_spend(f"'{date.today().strftime('%Y-%m')}-01'")


def check_budget(
    daily_limit: float | None = None,
    monthly_limit: float | None = None,
) -> dict[str, float]:
    """
    Check current spend against limits.  Raises BudgetExceededError if exceeded.

    Args:
        daily_limit:   override DAILY_BUDGET_USD from cost_tracker
        monthly_limit: override MONTHLY_BUDGET_USD from cost_tracker

    Returns:
        {"daily_spend": ..., "monthly_spend": ..., "daily_remaining": ..., "monthly_remaining": ...}
    """
    from app.modules.llm.cost_tracker import DAILY_BUDGET_USD, MONTHLY_BUDGET_USD

    daily_cap   = daily_limit   or DAILY_BUDGET_USD
    monthly_cap = monthly_limit or MONTHLY_BUDGET_USD

    daily   = get_daily_spend()
    monthly = get_monthly_spend()

    log.info("LLM budget: daily $%.4f / $%.2f  |  monthly $%.4f / $%.2f",
             daily, daily_cap, monthly, monthly_cap)

    if daily >= daily_cap:
        raise BudgetExceededError(
            f"Daily LLM budget exceeded: spent ${daily:.4f} of ${daily_cap:.2f}"
        )
    if monthly >= monthly_cap:
        raise BudgetExceededError(
            f"Monthly LLM budget exceeded: spent ${monthly:.4f} of ${monthly_cap:.2f}"
        )

    return {
        "daily_spend":       round(daily,   6),
        "monthly_spend":     round(monthly, 6),
        "daily_remaining":   round(daily_cap   - daily,   6),
        "monthly_remaining": round(monthly_cap - monthly, 6),
        "daily_cap":         daily_cap,
        "monthly_cap":       monthly_cap,
    }
