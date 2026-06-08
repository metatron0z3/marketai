"""research_node — 1 LLM call per run; synthesises cross-symbol research context."""
from __future__ import annotations

import logging

from app.modules.agents.graph.models import ResearchContext
from app.modules.agents.graph.prompts import build_research_prompt
from app.modules.agents.graph.state import GraphState
from app.modules.llm.model_factory import get_agent_model

log = logging.getLogger(__name__)


def _run_sector_contagion(flagged: list[dict]) -> dict:
    try:
        from app.modules.tos.ml.research.sector_contagion import run_contagion
        symbols = list({s["symbol"] for s in flagged})
        return run_contagion(symbols) or {}
    except Exception as exc:
        log.warning("sector_contagion failed: %s", exc)
        return {}


def _run_gamma_squeeze(flagged: list[dict]) -> dict:
    try:
        from app.modules.tos.ml.research.gamma_squeeze import run_squeeze_scan
        symbols = list({s["symbol"] for s in flagged})
        return run_squeeze_scan(symbols) or {}
    except Exception as exc:
        log.warning("gamma_squeeze failed: %s", exc)
        return {}


def _run_granger(flagged: list[dict]) -> dict:
    try:
        from app.modules.tos.ml.research.granger_causality import run_granger
        symbols = list({s["symbol"] for s in flagged})
        return run_granger(symbols) or {}
    except Exception as exc:
        log.warning("granger_causality failed: %s", exc)
        return {}


def _get_regime(scored_batches: list[dict]) -> dict:
    """Extract the most common regime name from scored batches."""
    from collections import Counter
    regimes: list[str] = []
    for batch in scored_batches:
        for sig in batch.get("scored", []):
            r = sig.get("regime_name")
            if r:
                regimes.append(r)
    if not regimes:
        return {"regime": "unknown"}
    top = Counter(regimes).most_common(1)[0][0]
    return {"regime": top, "sample_size": len(regimes)}


def research_node(state: GraphState) -> dict:
    if state.get("dry_run"):
        log.info("research_node: dry_run — skipping LLM call")
        return {"research_context": {"dominant_theme": "dry_run", "contagion_links": [],
                                     "squeeze_risk_tickers": [], "granger_leads": [],
                                     "regime_note": "dry_run"}}

    flagged   = state.get("flagged_signals", [])
    scored    = state.get("scored_batches",  [])
    alias     = state.get("model_aliases", {}).get("research", "sonnet")

    contagion = _run_sector_contagion(flagged)
    squeeze   = _run_gamma_squeeze(flagged)
    granger   = _run_granger(flagged)
    regime    = _get_regime(scored)

    messages = build_research_prompt(flagged[:10], contagion, squeeze, granger, regime)

    llm = get_agent_model("research", override=alias)
    try:
        result: ResearchContext = llm.with_structured_output(ResearchContext).invoke(messages)
        log.info("research_node: theme=%r, %d contagion links",
                 result.dominant_theme, len(result.contagion_links))
        return {"research_context": result.model_dump()}
    except Exception as exc:
        log.error("research_node LLM call failed: %s", exc)
        return {"research_context": None, "errors": [f"research_node: {exc}"]}
