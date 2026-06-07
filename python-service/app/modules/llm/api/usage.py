"""
LLM cost observability endpoints.

GET /llm/usage/daily   — spend breakdown for the last N days
GET /llm/usage/monthly — spend breakdown for the last N months
GET /llm/budget        — current spend vs. limits
GET /llm/audit         — raw audit log (paginated)
"""
import os
from datetime import date

import requests as http_requests
from fastapi import APIRouter, HTTPException, Query

router = APIRouter()

QUESTDB_HOST = os.getenv("QUESTDB_HOST", "questdb")
_BASE = f"http://{QUESTDB_HOST}:9000/exec"


def _qdb(sql: str) -> list[dict]:
    try:
        r = http_requests.get(_BASE, params={"query": sql}, timeout=10)
        r.raise_for_status()
        data = r.json()
        cols = [c["name"] for c in data.get("columns", [])]
        return [dict(zip(cols, row)) for row in data.get("dataset", [])]
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"QuestDB error: {exc}")


@router.get("/usage/daily")
def daily_usage(days: int = Query(default=30, ge=1, le=365)):
    """Cost and token usage grouped by day and model, last N days."""
    sql = f"""
        SELECT
            called_at::date          AS day,
            model,
            caller,
            count()                  AS calls,
            sum(prompt_tokens)       AS prompt_tokens,
            sum(completion_tokens)   AS completion_tokens,
            sum(cost_usd)            AS cost_usd,
            avg(latency_ms)          AS avg_latency_ms,
            sum(CASE WHEN status = 'error' THEN 1 ELSE 0 END) AS errors
        FROM   llm_audit_log
        WHERE  called_at >= dateadd('d', -{days}, now())
        GROUP  BY day, model, caller
        ORDER  BY day DESC, cost_usd DESC
    """
    rows = _qdb(sql)
    return {"days": days, "rows": rows, "total_cost_usd": sum(r["cost_usd"] for r in rows)}


@router.get("/usage/monthly")
def monthly_usage(months: int = Query(default=6, ge=1, le=24)):
    """Cost and token usage grouped by month and model."""
    sql = f"""
        SELECT
            to_str(called_at, 'yyyy-MM')  AS month,
            model,
            caller,
            count()                        AS calls,
            sum(prompt_tokens)             AS prompt_tokens,
            sum(completion_tokens)         AS completion_tokens,
            sum(cost_usd)                  AS cost_usd,
            avg(latency_ms)                AS avg_latency_ms
        FROM   llm_audit_log
        WHERE  called_at >= dateadd('M', -{months}, now())
        GROUP  BY month, model, caller
        ORDER  BY month DESC, cost_usd DESC
    """
    rows = _qdb(sql)
    return {"months": months, "rows": rows, "total_cost_usd": sum(r["cost_usd"] for r in rows)}


@router.get("/budget")
def budget_status():
    """Current daily and monthly spend vs. configured limits."""
    from app.modules.llm.budget_guard import get_daily_spend, get_monthly_spend
    from app.modules.llm.cost_tracker import DAILY_BUDGET_USD, MONTHLY_BUDGET_USD

    daily   = get_daily_spend()
    monthly = get_monthly_spend()

    return {
        "daily": {
            "spent":     round(daily,   6),
            "limit":     DAILY_BUDGET_USD,
            "remaining": round(DAILY_BUDGET_USD   - daily,   6),
            "pct_used":  round(daily   / DAILY_BUDGET_USD   * 100, 1),
        },
        "monthly": {
            "spent":     round(monthly, 6),
            "limit":     MONTHLY_BUDGET_USD,
            "remaining": round(MONTHLY_BUDGET_USD - monthly, 6),
            "pct_used":  round(monthly / MONTHLY_BUDGET_USD * 100, 1),
        },
    }


@router.get("/audit")
def audit_log(
    limit:  int             = Query(default=100, ge=1, le=1000),
    symbol: str | None      = Query(default=None),
    caller: str | None      = Query(default=None),
    status: str | None      = Query(default=None),
    since:  date | None     = Query(default=None),
):
    """Paginated raw audit log from llm_audit_log."""
    filters = ["1=1"]
    if symbol:
        filters.append(f"symbol = '{symbol}'")
    if caller:
        filters.append(f"caller = '{caller}'")
    if status:
        filters.append(f"status = '{status}'")
    if since:
        filters.append(f"called_at >= '{since}'")

    where = " AND ".join(filters)
    sql = f"""
        SELECT called_at, caller, model, symbol, prompt_tokens, completion_tokens,
               cost_usd, latency_ms, status, error_msg, flow_run_id
        FROM   llm_audit_log
        WHERE  {where}
        ORDER  BY called_at DESC
        LIMIT  {limit}
    """
    rows = _qdb(sql)
    return {"count": len(rows), "rows": rows}


@router.get("/enrichment/summary")
def enrichment_summary(
    symbol: str | None = Query(default=None),
    days:   int        = Query(default=7, ge=1, le=90),
):
    """Enriched signal summary: count by activity_type and avg conviction."""
    sym_filter = f"AND symbol = '{symbol}'" if symbol else ""
    sql = f"""
        SELECT
            symbol,
            activity_type,
            count()                  AS count,
            avg(conviction_score)    AS avg_conviction,
            sum(cost_usd)            AS cost_usd
        FROM   options_enrichment
        WHERE  enriched_at >= dateadd('d', -{days}, now())
        {sym_filter}
        GROUP  BY symbol, activity_type
        ORDER  BY symbol, avg_conviction DESC
    """
    return {"days": days, "rows": _qdb(sql)}
