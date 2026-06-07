"""
POST /options/enrichment/run       — trigger enrichment for a symbol/date range
GET  /options/enriched-signals     — retrieve enriched signals
GET  /options/enrichment/synthesis — daily synthesis narrative
"""
from datetime import date

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query

router = APIRouter()


@router.post("/enrichment/run")
def run_enrichment(
    symbol:     str,
    start_date: date  = Query(...),
    end_date:   date  = Query(...),
    dry_run:    bool  = Query(default=False),
    background_tasks: BackgroundTasks = None,
):
    """
    Enrich options_features rows with LLM classification for a given symbol + date range.
    Runs synchronously; for long ranges use the Prefect flow instead.
    """
    from app.modules.options.services.llm_enrichment import enrich_symbol
    try:
        result = enrich_symbol(
            symbol=symbol,
            start_date=str(start_date),
            end_date=str(end_date),
            dry_run=dry_run,
        )
        return result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/enriched-signals")
def get_enriched_signals(
    symbol:       str,
    n:            int        = Query(default=20, ge=1, le=200),
    activity_type: str | None = Query(default=None),
    min_conviction: float    = Query(default=0.0, ge=0.0, le=1.0),
    since:        date | None = Query(default=None),
):
    """Return the most recent enriched signals for a symbol."""
    import os
    import requests
    host = os.getenv("QUESTDB_HOST", "questdb")

    filters = [f"symbol = '{symbol}'", f"conviction_score >= {min_conviction}"]
    if activity_type:
        filters.append(f"activity_type = '{activity_type}'")
    if since:
        filters.append(f"enriched_at >= '{since}'")

    sql = f"""
        SELECT enriched_at, ts_event, symbol, strike, expiration, put_call,
               activity_type, conviction_score, narrative, model, cost_usd
        FROM   options_enrichment
        WHERE  {' AND '.join(filters)}
        ORDER  BY conviction_score DESC
        LIMIT  {n}
    """
    r = requests.get(f"http://{host}:9000/exec", params={"query": sql}, timeout=15)
    r.raise_for_status()
    data = r.json()
    cols = [c["name"] for c in data.get("columns", [])]
    rows = [dict(zip(cols, row)) for row in data.get("dataset", [])]
    return {"symbol": symbol, "count": len(rows), "signals": rows}


@router.get("/enrichment/synthesis")
def get_daily_synthesis(
    symbol:      str,
    target_date: date = Query(default=None),
):
    """Generate (or return cached) daily synthesis narrative for a symbol."""
    from app.modules.options.services.llm_enrichment import synthesize_daily_summary
    from datetime import date as date_cls
    d = str(target_date or date_cls.today())
    try:
        narrative = synthesize_daily_summary(symbol=symbol, target_date=d)
        return {"symbol": symbol, "date": d, "narrative": narrative}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
