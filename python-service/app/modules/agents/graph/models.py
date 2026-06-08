"""
Pydantic output models for LangGraph LLM nodes.

All LLM nodes use llm.with_structured_output(Model) — these models are the
framework-guaranteed schema. No JSON parsing or regex fallbacks needed.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


# ── research_node ─────────────────────────────────────────────────────────────

class ContagionLink(BaseModel):
    source: str
    target: str
    lag_hours: int
    confidence: float


class GrangerLead(BaseModel):
    feature: str
    target_return: str      # "1d" | "5d"
    p_value: float


class ResearchContext(BaseModel):
    dominant_theme: str
    contagion_links: list[ContagionLink]
    squeeze_risk_tickers: list[str]
    granger_leads: list[GrangerLead]
    regime_note: str


# ── strategy_node ─────────────────────────────────────────────────────────────

class PositionSizing(BaseModel):
    kelly_fraction: float
    recommended_pct: str     # e.g. "2.0%"
    max_contracts: int


class TradeParams(BaseModel):
    ticker: str
    direction: Literal["CALL", "PUT"]
    entry_condition: str
    strike_preference: str
    dte_target: str
    position_sizing: PositionSizing
    stop_loss: str
    profit_target: str
    hedges: str
    rationale: str
    conviction_score: float
    signal_id: str


# ── synthesis_node ────────────────────────────────────────────────────────────

class SetupSummary(BaseModel):
    ticker: str
    direction: str
    thesis: str
    key_risk: str


class DailyBrief(BaseModel):
    regime_summary: str
    top_3_setups: list[SetupSummary]
    macro_risk_flags: list[str]
    sector_rotation: str
    daily_narrative: str     # 2-3 sentences


# ── archive_node ──────────────────────────────────────────────────────────────

class GlossaryEntry(BaseModel):
    term: str
    definition: str
    concrete_example: str
    related_terms: list[str]
    source_file: str | None


class Milestone(BaseModel):
    date: str
    title: str
    description: str
    technical_detail: str
    impact: str


class TechnicalExplainer(BaseModel):
    topic: str
    audience: str
    body: str
    key_invariants: list[str]
    gotchas: list[str]


class PerformanceSummary(BaseModel):
    period: str
    signals_flagged: int
    avg_conviction_score: float
    top_tickers: list[str]
    outcomes_available: bool
    narrative: str


class ArchiveReport(BaseModel):
    generated_at: str
    milestones: list[Milestone]
    glossary_updates: list[GlossaryEntry]
    technical_explainers: list[TechnicalExplainer]
    performance_summary: PerformanceSummary
    next_focus: str
