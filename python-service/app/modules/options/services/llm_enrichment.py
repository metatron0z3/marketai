"""
LLM enrichment service — uses Claude Haiku to classify and narrate high-signal
options activity from options_features rows.

Signal filter: rvol >= 3.0 AND premium_flow >= 50000
Model: claude-haiku-4-5 (bulk), claude-sonnet-4-6 (daily synthesis summary)

All calls are logged to llm_audit_log via LLMClient. Idempotent — skips rows
already present in options_enrichment.
"""
import json
import logging
import os
from datetime import date, datetime, timezone

log = logging.getLogger(__name__)

BULK_MODEL    = "claude-haiku-4-5-20251001"
SYNTH_MODEL   = "claude-sonnet-4-6"
RVOL_MIN      = 3.0
PREMIUM_MIN   = 50_000.0
MAX_TOKENS    = 300


CLASSIFY_PROMPT = """\
You are an options flow analyst. Given the following options bar data, classify the activity and write a brief narrative.

Symbol: {symbol}
Strike: {strike}  Expiry: {expiration}  Type: {put_call}  DTE: {days_to_exp}
RVOL (relative volume): {rvol:.1f}x  Premium Flow: ${premium_flow:,.0f}
Vol/OI Ratio: {vol_oi_ratio:.2f}  Sweep Intensity: {sweep_intensity:.2f}
Underlying move context: aggressor ratio {aggressor_ratio:.2f}

Respond with ONLY valid JSON, no markdown:
{{
  "activity_type": "<accumulation|sweep|exit|noise>",
  "conviction_score": <0.0-1.0>,
  "narrative": "<1-2 sentences a trader can act on>"
}}"""


def _build_prompt(row: dict) -> str:
    return CLASSIFY_PROMPT.format(**row)


def _parse_response(text: str) -> dict:
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        import re
        m = re.search(r'\{.*\}', text, re.DOTALL)
        if m:
            return json.loads(m.group())
        raise ValueError(f"Could not parse LLM response: {text[:200]}")


def _fetch_unenriched(symbol: str, start_date: str, end_date: str) -> list[dict]:
    host = os.getenv("QUESTDB_HOST", "questdb")
    import requests
    sql = f"""
        SELECT f.ts_event, f.symbol, f.strike, f.expiration, f.put_call,
               f.rvol, f.vol_oi_ratio, f.premium_flow, f.sweep_intensity,
               f.aggressor_ratio, f.delta_exposure, f.iv_rank, f.days_to_exp
        FROM   options_features f
        WHERE  f.symbol = '{symbol}'
          AND  f.ts_event >= '{start_date}'
          AND  f.ts_event <  dateadd('d', 1, '{end_date}')
          AND  f.rvol          >= {RVOL_MIN}
          AND  f.premium_flow  >= {PREMIUM_MIN}
          AND  f.ts_event NOT IN (
              SELECT ts_event FROM options_enrichment
              WHERE  symbol = '{symbol}'
                AND  enriched_at::date >= '{start_date}'
          )
        ORDER  BY f.ts_event
    """
    resp = requests.get(f"http://{host}:9000/exec", params={"query": sql}, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    cols = [c["name"] for c in data.get("columns", [])]
    return [dict(zip(cols, row)) for row in data.get("dataset", [])]


def _write_enrichment(rows: list[dict]) -> None:
    if not rows:
        return
    from questdb.ingress import Sender, TimestampNanos
    conf = os.getenv("QDB_CLIENT_CONF", "http::addr=questdb:9000;")
    with Sender.from_conf(conf) as sender:
        for r in rows:
            ts_ns = int(datetime.now(tz=timezone.utc).timestamp() * 1e9)
            sender.row(
                "options_enrichment",
                symbols={
                    "symbol":        r["symbol"],
                    "put_call":      r["put_call"],
                    "activity_type": r["activity_type"],
                    "model":         r["model"],
                },
                columns={
                    "ts_event":          r["ts_event"],
                    "strike":            float(r["strike"]),
                    "expiration":        str(r["expiration"]),
                    "conviction_score":  float(r["conviction_score"]),
                    "narrative":         r["narrative"],
                    "prompt_tokens":     int(r["prompt_tokens"]),
                    "completion_tokens": int(r["completion_tokens"]),
                    "cost_usd":          float(r["cost_usd"]),
                    "latency_ms":        int(r["latency_ms"]),
                },
                at=TimestampNanos(ts_ns),
            )
        sender.flush()


def enrich_symbol(
    symbol: str,
    start_date: str,
    end_date: str,
    dry_run: bool = False,
) -> dict:
    """
    Classify and narrate all high-signal options_features rows for a symbol.

    Returns:
        {"symbol": ..., "processed": N, "skipped": N, "cost_usd": X.XX}
    """
    from app.modules.llm.audit import LLMClient
    from app.modules.llm.budget_guard import check_budget

    check_budget()

    rows = _fetch_unenriched(symbol, start_date, end_date)
    log.info("%s: %d rows to enrich (%s → %s)", symbol, len(rows), start_date, end_date)

    if not rows or dry_run:
        return {"symbol": symbol, "processed": 0, "skipped": len(rows), "cost_usd": 0.0}

    client = LLMClient(caller="options_enrichment", symbol=symbol)
    results = []
    total_cost = 0.0

    for row in rows:
        prompt = _build_prompt(row)
        try:
            resp = client.create(
                model=BULK_MODEL,
                max_tokens=MAX_TOKENS,
                messages=[{"role": "user", "content": prompt}],
            )
            parsed = _parse_response(resp.content[0].text)
            results.append({
                **row,
                "activity_type":   parsed.get("activity_type", "noise"),
                "conviction_score": float(parsed.get("conviction_score", 0.0)),
                "narrative":       parsed.get("narrative", ""),
                "model":           BULK_MODEL,
                "prompt_tokens":   resp.audit.prompt_tokens,
                "completion_tokens": resp.audit.completion_tokens,
                "cost_usd":        resp.audit.cost_usd,
                "latency_ms":      resp.audit.latency_ms,
            })
            total_cost += resp.audit.cost_usd
        except Exception as exc:
            log.warning("Enrichment failed for %s %s: %s", symbol, row.get("ts_event"), exc)

    _write_enrichment(results)
    log.info("%s: enriched %d rows, total cost $%.6f", symbol, len(results), total_cost)
    return {"symbol": symbol, "processed": len(results), "skipped": 0, "cost_usd": total_cost}


def synthesize_daily_summary(symbol: str, target_date: str) -> str:
    """
    Use Claude Sonnet to write a ~paragraph daily options flow summary for a symbol,
    based on enriched signals from that day. Returns the narrative text.
    """
    from app.modules.llm.audit import LLMClient

    host = os.getenv("QUESTDB_HOST", "questdb")
    import requests
    sql = f"""
        SELECT activity_type, conviction_score, narrative, put_call, strike, expiration
        FROM   options_enrichment
        WHERE  symbol = '{symbol}'
          AND  enriched_at::date = '{target_date}'
        ORDER  BY conviction_score DESC
        LIMIT  20
    """
    resp = requests.get(f"http://{host}:9000/exec", params={"query": sql}, timeout=15)
    data = resp.json()
    cols = [c["name"] for c in data.get("columns", [])]
    signals = [dict(zip(cols, row)) for row in data.get("dataset", [])]

    if not signals:
        return f"No enriched signals for {symbol} on {target_date}."

    signal_text = "\n".join(
        f"- [{r['activity_type'].upper()} {r['put_call']} {r['strike']} exp {r['expiration']}]"
        f" conviction={r['conviction_score']:.2f}: {r['narrative']}"
        for r in signals
    )

    prompt = (
        f"Today's enriched options signals for {symbol} ({target_date}):\n\n"
        f"{signal_text}\n\n"
        "Write a concise 2-3 sentence daily options flow summary for a trader. "
        "Focus on dominant theme, direction bias, and any high-conviction clusters."
    )

    client = LLMClient(caller="daily_synthesis", symbol=symbol)
    resp = client.create(
        model=SYNTH_MODEL,
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text.strip()
