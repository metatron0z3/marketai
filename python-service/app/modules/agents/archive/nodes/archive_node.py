"""
archive_node — 3-5 LLM calls per run.

Responsibilities:
  Pass 1: development log — git log + WORKLOG → list[Milestone]
  Pass 2: glossary update — new terms since last archive → list[GlossaryEntry]
  Pass 3: technical explainer — one undocumented subsystem per run → TechnicalExplainer
  Pass 4: performance summary — code only (reads QuestDB)

Model: sonnet (passes 1+2+4), opus override for pass 3 (ARCHIVE_DEEP_MODEL).
"""
from __future__ import annotations

import logging
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from app.modules.agents.archive.state import ArchiveGraphState
from app.modules.agents.graph.models import (
    ArchiveReport,
    GlossaryEntry,
    Milestone,
    PerformanceSummary,
    TechnicalExplainer,
)
from app.modules.agents.graph.prompts import (
    build_explainer_prompt,
    build_glossary_prompt,
    build_milestone_prompt,
)
from app.modules.llm.model_factory import get_agent_model

log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).parents[6]          # python-service/app/modules/agents/archive/nodes → repo root
WORKLOG   = REPO_ROOT / "docs" / "agentic" / "WORKLOG.md"
GLOSSARY  = REPO_ROOT / "docs" / "glossary.html"

EXPLAINER_TOPICS = [
    "ConvictionScorer formula",
    "LangGraph StateGraph topology",
    "SHAP feature attribution in options signals",
    "QuestDB ILP ingestion pattern",
    "walk-forward cross-validation design",
    "Half-Kelly position sizing implementation",
    "Sector contagion detection algorithm",
    "Gamma squeeze scan methodology",
]


def _read_git_log(since: str) -> str:
    try:
        result = subprocess.run(
            ["git", "log", f"--since={since}", "--oneline", "--no-merges"],
            capture_output=True, text=True, cwd=str(REPO_ROOT), timeout=15,
        )
        return result.stdout[:8000]
    except Exception as exc:
        log.warning("git log failed: %s", exc)
        return ""


def _read_worklog() -> str:
    try:
        return WORKLOG.read_text(encoding="utf-8")[:4000]
    except Exception:
        return ""


def _extract_existing_glossary_terms() -> list[str]:
    try:
        html = GLOSSARY.read_text(encoding="utf-8")
        return re.findall(r'<dt[^>]*>(.*?)</dt>', html, re.DOTALL)
    except Exception:
        return []


def _discover_new_terms(since: str) -> list[str]:
    """Scan recent code and doc changes for potential new glossary terms."""
    try:
        result = subprocess.run(
            ["git", "diff", f"HEAD~10..HEAD", "--name-only"],
            capture_output=True, text=True, cwd=str(REPO_ROOT), timeout=10,
        )
        changed = result.stdout.strip().split("\n")
        # Heuristic: any .py files with new class/def names are candidate terms
        new_terms = set()
        for f in changed:
            if f.endswith(".py"):
                try:
                    content = (REPO_ROOT / f).read_text(encoding="utf-8")
                    new_terms |= set(re.findall(r'(?:class|def)\s+([A-Z][A-Za-z0-9]+)', content))
                except Exception:
                    pass
        # Filter out obvious non-glossary terms
        ignore = {"BaseModel", "TypedDict", "Exception", "Response", "Request"}
        return list(new_terms - ignore)[:15]
    except Exception as exc:
        log.warning("new term discovery failed: %s", exc)
        return []


def _pick_explainer_topic(state: ArchiveGraphState) -> str:
    """Pick the next undocumented topic in round-robin order."""
    existing = _extract_existing_glossary_terms()
    for topic in EXPLAINER_TOPICS:
        if not any(topic.lower() in t.lower() for t in existing):
            return topic
    return EXPLAINER_TOPICS[0]


def _read_performance_data(since: str) -> PerformanceSummary:
    """Read conviction scores and signal counts from QuestDB."""
    import os, requests as req
    host = os.getenv("QUESTDB_HOST", "questdb")
    try:
        sql = (
            f"SELECT count(), avg(conviction_score), max(symbol) "
            f"FROM agent_trade_params "
            f"WHERE generated_at >= '{since}' "
            f"LIMIT 1"
        )
        resp = req.get(f"http://{host}:9000/exec", params={"query": sql}, timeout=5)
        data = resp.json().get("dataset", [[0, 0.0, ""]])[0]
        count, avg_conv, _ = data
    except Exception:
        count, avg_conv = 0, 0.0

    return PerformanceSummary(
        period=f"{since} to {datetime.now(timezone.utc).date().isoformat()}",
        signals_flagged=int(count or 0),
        avg_conviction_score=round(float(avg_conv or 0), 4),
        top_tickers=[],
        outcomes_available=False,
        narrative="Performance data not yet available — real-data runs pending.",
    )


def archive_node(state: ArchiveGraphState) -> dict:
    if state.get("dry_run"):
        log.info("archive_node: dry_run — skipping all LLM calls")
        return {"archive_report": None}

    since   = state.get("last_archive_date", "2026-01-01")
    alias   = state.get("model_aliases", {}).get("archive", "sonnet")
    alias_d = state.get("model_aliases", {}).get("archive_deep", "opus")

    llm      = get_agent_model("archive",      override=alias)
    llm_deep = get_agent_model("archive_deep", override=alias_d)

    git_log = _read_git_log(since)
    worklog = _read_worklog()
    errors: list[str] = []

    # Pass 1: milestones
    milestones: list[Milestone] = []
    try:
        milestones = llm.with_structured_output(list[Milestone]).invoke(
            build_milestone_prompt(git_log, worklog)
        )
        log.info("archive_node pass1: %d milestones", len(milestones))
    except Exception as exc:
        log.error("archive_node pass1 (milestones) failed: %s", exc)
        errors.append(f"milestones: {exc}")

    # Pass 2: glossary
    glossary_updates: list[GlossaryEntry] = []
    try:
        existing = _extract_existing_glossary_terms()
        new_terms = _discover_new_terms(since)
        if new_terms:
            glossary_updates = llm.with_structured_output(list[GlossaryEntry]).invoke(
                build_glossary_prompt(existing, new_terms)
            )
            log.info("archive_node pass2: %d glossary entries", len(glossary_updates))
    except Exception as exc:
        log.error("archive_node pass2 (glossary) failed: %s", exc)
        errors.append(f"glossary: {exc}")

    # Pass 3: technical explainer (deep model)
    explainers: list[TechnicalExplainer] = []
    try:
        topic = _pick_explainer_topic(state)
        result = llm_deep.with_structured_output(TechnicalExplainer).invoke(
            build_explainer_prompt(topic, {})
        )
        explainers = [result]
        log.info("archive_node pass3: explainer for %r", topic)
    except Exception as exc:
        log.error("archive_node pass3 (explainer) failed: %s", exc)
        errors.append(f"explainer: {exc}")

    # Pass 4: performance summary (code only)
    perf = _read_performance_data(since)

    report = ArchiveReport(
        generated_at=datetime.now(timezone.utc).isoformat(),
        milestones=milestones,
        glossary_updates=glossary_updates,
        technical_explainers=explainers,
        performance_summary=perf,
        next_focus=_pick_explainer_topic(state),
    )

    return {"archive_report": report.model_dump(), "errors": errors}
