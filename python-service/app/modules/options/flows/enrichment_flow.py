"""
Prefect Flow — Daily LLM enrichment + cost observability.

Schedule: runs after EOD feature computation (22:30 ET daily).
  1. check_budget — abort if daily/monthly limit hit
  2. enrich all watchlist symbols for yesterday
  3. synthesize daily summaries
  4. emit cost report to logs
"""
import logging
from datetime import date, timedelta

from prefect import flow, get_run_logger, task

log = logging.getLogger(__name__)

ENRICH_SYMBOLS = ["TSLA", "NVDA", "SPY", "QQQ", "AAPL", "AMD", "META", "AMZN", "MSFT"]


@task(name="check_llm_budget", retries=0)
def check_llm_budget() -> dict:
    from app.modules.llm.budget_guard import BudgetExceededError, check_budget
    logger = get_run_logger()
    try:
        status = check_budget()
        logger.info(
            "LLM budget OK — daily: $%.4f / $%.2f  monthly: $%.4f / $%.2f",
            status["daily_spend"], status["daily_cap"],
            status["monthly_spend"], status["monthly_cap"],
        )
        return status
    except BudgetExceededError as exc:
        logger.error("Budget exceeded — skipping enrichment: %s", exc)
        raise


@task(name="enrich_symbol", retries=1, retry_delay_seconds=30)
def enrich_symbol_task(symbol: str, target_date: str) -> dict:
    from app.modules.options.services.llm_enrichment import enrich_symbol
    logger = get_run_logger()
    result = enrich_symbol(symbol=symbol, start_date=target_date, end_date=target_date)
    logger.info("%s: %d enriched, $%.6f", symbol, result["processed"], result["cost_usd"])
    return result


@task(name="synthesize_summary", retries=1)
def synthesize_summary_task(symbol: str, target_date: str) -> str:
    from app.modules.options.services.llm_enrichment import synthesize_daily_summary
    return synthesize_daily_summary(symbol=symbol, target_date=target_date)


@task(name="emit_cost_report")
def emit_cost_report(enrich_results: list[dict]) -> dict:
    logger = get_run_logger()
    from app.modules.llm.budget_guard import get_daily_spend, get_monthly_spend
    from app.modules.llm.cost_tracker import DAILY_BUDGET_USD, MONTHLY_BUDGET_USD

    total_enriched = sum(r["processed"] for r in enrich_results)
    total_cost     = sum(r["cost_usd"] for r in enrich_results)
    daily_spend    = get_daily_spend()
    monthly_spend  = get_monthly_spend()

    report = {
        "enriched_today":    total_enriched,
        "enrichment_cost":   round(total_cost,   6),
        "daily_spend":       round(daily_spend,  6),
        "monthly_spend":     round(monthly_spend, 6),
        "daily_pct":         round(daily_spend   / DAILY_BUDGET_USD   * 100, 1),
        "monthly_pct":       round(monthly_spend / MONTHLY_BUDGET_USD * 100, 1),
    }

    logger.info(
        "Cost report: %d signals enriched | $%.6f today ($%.6f/mo) | "
        "daily %s%% | monthly %s%%",
        total_enriched, daily_spend, monthly_spend,
        report["daily_pct"], report["monthly_pct"],
    )

    if report["daily_pct"] > 80:
        logger.warning("Daily budget at %s%% — approaching limit", report["daily_pct"])
    if report["monthly_pct"] > 75:
        logger.warning("Monthly budget at %s%% — approaching limit", report["monthly_pct"])

    return report


@flow(
    name="options_enrichment_daily",
    description="Nightly LLM enrichment of high-signal options bars + cost reporting",
    log_prints=True,
)
def enrichment_daily_flow(
    target_date: str | None = None,
    symbols: list[str] | None = None,
    dry_run: bool = False,
) -> dict:
    logger = get_run_logger()
    d = target_date or str(date.today() - timedelta(days=1))
    syms = symbols or ENRICH_SYMBOLS

    logger.info("Enrichment flow: %d symbols for %s (dry_run=%s)", len(syms), d, dry_run)

    budget = check_llm_budget()

    enrich_results = [enrich_symbol_task(sym, d) for sym in syms]

    syntheses = {}
    for sym in syms:
        try:
            syntheses[sym] = synthesize_summary_task(sym, d)
        except Exception as exc:
            logger.warning("Synthesis failed for %s: %s", sym, exc)

    report = emit_cost_report(enrich_results)

    return {
        "date":         d,
        "symbols":      syms,
        "report":       report,
        "budget":       budget,
        "syntheses":    syntheses,
    }


if __name__ == "__main__":
    enrichment_daily_flow()
