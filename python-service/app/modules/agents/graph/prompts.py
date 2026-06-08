"""
Prompt builders for LangGraph LLM nodes.

Each function returns a list of LangChain messages.
Prompts follow the three-part pattern: system role → quantitative context → instruction.
"""
from __future__ import annotations

import json
from langchain_core.messages import HumanMessage, SystemMessage


# ── research_node ─────────────────────────────────────────────────────────────

_RESEARCH_SYSTEM = (
    "You are a quantitative options analyst. "
    "Return ONLY valid structured output matching the schema. "
    "Never include explanations, markdown fences, or keys not in the schema."
)


def build_research_prompt(
    flagged_signals: list[dict],
    contagion: dict,
    squeeze: dict,
    granger: dict,
    regime: dict,
) -> list:
    context = {
        "flagged_signals":  flagged_signals[:10],
        "sector_contagion": contagion,
        "gamma_squeeze":    squeeze,
        "granger_causality": granger,
        "market_regime":    regime,
    }
    instruction = (
        "Produce a ResearchContext with these exact fields: "
        "dominant_theme (str), contagion_links (list[ContagionLink]), "
        "squeeze_risk_tickers (list[str]), granger_leads (list[GrangerLead]), "
        "regime_note (str). "
        "Base your analysis strictly on the quantitative inputs provided."
    )
    return [
        SystemMessage(content=_RESEARCH_SYSTEM),
        HumanMessage(content=f"CONTEXT:\n{json.dumps(context, default=str)}\n\n{instruction}"),
    ]


# ── strategy_node ─────────────────────────────────────────────────────────────

_STRATEGY_SYSTEM = (
    "You are a disciplined options trader specialising in unusual-volume setups. "
    "Return ONLY valid structured output matching the schema. "
    "Position sizing uses ½ Kelly with a hard cap at MAX_POSITION_PCT. "
    "Always recommend a hedge when vega exposure is high."
)


def build_strategy_prompt(
    signal: dict,
    research_context: dict | None,
    kelly_fraction: float,
) -> list:
    context = {
        "signal":           signal,
        "research_context": research_context or {},
        "kelly_fraction":   round(kelly_fraction, 4),
        "max_position_pct": 5.0,
    }
    instruction = (
        "Produce a TradeParams with these exact fields: "
        "ticker, direction (CALL|PUT), entry_condition, strike_preference, "
        "dte_target, position_sizing (kelly_fraction, recommended_pct, max_contracts), "
        "stop_loss, profit_target, hedges, rationale, conviction_score, signal_id."
    )
    return [
        SystemMessage(content=_STRATEGY_SYSTEM),
        HumanMessage(content=f"CONTEXT:\n{json.dumps(context, default=str)}\n\n{instruction}"),
    ]


# ── synthesis_node ────────────────────────────────────────────────────────────

_SYNTHESIS_SYSTEM = (
    "You are a senior portfolio manager writing a nightly options analysis brief. "
    "Return ONLY valid structured output matching the schema. "
    "Be concise — daily_narrative is 2-3 sentences maximum."
)


def build_synthesis_prompt(
    target_date: str,
    trade_params: list[dict],
    research_context: dict | None,
) -> list:
    context = {
        "date":             target_date,
        "trade_params":     trade_params,
        "research_context": research_context or {},
    }
    instruction = (
        "Produce a DailyBrief with these exact fields: "
        "regime_summary, top_3_setups (list[SetupSummary] with ticker/direction/thesis/key_risk), "
        "macro_risk_flags (list[str]), sector_rotation (str), daily_narrative (str, 2-3 sentences)."
    )
    return [
        SystemMessage(content=_SYNTHESIS_SYSTEM),
        HumanMessage(content=f"CONTEXT:\n{json.dumps(context, default=str)}\n\n{instruction}"),
    ]


# ── archive_node ─────────────────────────────────────────────────────────────

_ARCHIVE_MILESTONE_SYSTEM = (
    "You are a technical historian documenting a quantitative trading system. "
    "Return ONLY valid structured output. "
    "Milestones must be factual — derive them from the git log and worklog provided."
)

_ARCHIVE_GLOSSARY_SYSTEM = (
    "You are maintaining a technical glossary for an options trading platform. "
    "Return ONLY valid structured output. "
    "Each definition must include a concrete example (real ticker, real number, or real formula). "
    "Do not repeat terms already in the existing glossary."
)

_ARCHIVE_EXPLAINER_SYSTEM = (
    "You are writing a technical explainer for an informed developer reading a codebase. "
    "Return ONLY valid structured output. "
    "body is 3-6 paragraphs of markdown. "
    "key_invariants and gotchas are the non-obvious parts a reader needs."
)


def build_milestone_prompt(git_log: str, worklog: str) -> list:
    context = {"git_log": git_log[-8000:], "worklog": worklog[-4000:]}
    instruction = (
        "Produce a list[Milestone]. Each Milestone: "
        "date (YYYY-MM-DD), title (one line), description (2-4 sentences of what changed and why), "
        "technical_detail (the non-obvious part), impact (what this unlocked or fixed)."
    )
    return [
        SystemMessage(content=_ARCHIVE_MILESTONE_SYSTEM),
        HumanMessage(content=f"CONTEXT:\n{json.dumps(context)}\n\n{instruction}"),
    ]


def build_glossary_prompt(existing_terms: list[str], new_terms: list[str]) -> list:
    context = {"existing_terms": existing_terms, "new_terms_to_define": new_terms}
    instruction = (
        "Produce a list[GlossaryEntry] for the new_terms_to_define only. "
        "Each entry: term, definition (2-3 sentences plain English), "
        "concrete_example (real ticker / number / formula), "
        "related_terms (list[str]), source_file (str or null)."
    )
    return [
        SystemMessage(content=_ARCHIVE_GLOSSARY_SYSTEM),
        HumanMessage(content=f"CONTEXT:\n{json.dumps(context)}\n\n{instruction}"),
    ]


def build_explainer_prompt(topic: str, source_snippets: dict[str, str]) -> list:
    context = {"topic": topic, "source_snippets": source_snippets}
    instruction = (
        "Produce a TechnicalExplainer: "
        "topic, audience ('informed developer, first time reading'), "
        "body (3-6 paragraphs markdown), "
        "key_invariants (list[str]), gotchas (list[str])."
    )
    return [
        SystemMessage(content=_ARCHIVE_EXPLAINER_SYSTEM),
        HumanMessage(content=f"CONTEXT:\n{json.dumps(context, default=str)}\n\n{instruction}"),
    ]
