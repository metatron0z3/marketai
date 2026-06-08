"""
archive_node — 2 LLM calls per run (Pass 3 moved to education_graph).

Responsibilities:
  Pass 1: development log — git log + WORKLOG → list[Milestone]
  Pass 2: glossary update — new terms since last archive → list[GlossaryEntry]
  Pass 3: (delegated) education_graph runs one explainer per archive cycle
           via next_unwritten_topic() — separate graph, separate LangSmith trace
  Pass 4: performance summary — code only (reads QuestDB)

Model: sonnet (both LLM passes), ARCHIVE_MODEL env var.
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
)
from app.modules.agents.graph.prompts import build_glossary_prompt, build_milestone_prompt
from app.modules.llm.model_factory import get_agent_model

log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).parents[6]   # …/archive/nodes → repo root
WORKLOG   = REPO_ROOT / "docs" / "agentic" / "WORKLOG.md"
GLOSSARY  = REPO_ROOT / "docs" / "glossary.html"


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
    """Scan recent changed .py files for new class/def names as glossary candidates."""
    try:
        result = subprocess.run(
            ["git", "diff", "HEAD~10..HEAD", "--name-only"],
            capture_output=True, text=True, cwd=str(REPO_ROOT), timeout=10,
        )
        changed = result.stdout.strip().split("\n")
        new_terms: set[str] = set()
        for f in changed:
            if f.endswith(".py"):
                try:
                    content = (REPO_ROOT / f).read_text(encoding="utf-8")
                    new_terms |= set(re.findall(r'(?:class|def)\s+([A-Z][A-Za-z0-9]+)', content))
                except Exception:
                    pass
        ignore = {"BaseModel", "TypedDict", "Exception", "Response", "Request"}
        return list(new_terms - ignore)[:15]
    except Exception as exc:
        log.warning("new term discovery failed: %s", exc)
        return []


def _read_performance_data(since: str) -> PerformanceSummary:
    import os
    import requests as req
    host = os.getenv("QUESTDB_HOST", "questdb")
    try:
        sql = (
            f"SELECT count(), avg(conviction_score) "
            f"FROM agent_trade_params "
            f"WHERE generated_at >= '{since}' "
            f"LIMIT 1"
        )
        resp = req.get(f"http://{host}:9000/exec", params={"query": sql}, timeout=5)
        data = resp.json().get("dataset", [[0, 0.0]])[0]
        count, avg_conv = data[0], data[1]
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


def _run_education_pass(state: ArchiveGraphState) -> None:
    """
    Trigger one education graph run for the next unwritten topic.
    Runs synchronously within the archive flow; logged as a separate LangSmith trace.
    """
    try:
        from langchain_core.runnables import RunnableConfig
        from app.modules.agents.education.education_graph import (
            build_education_graph,
            make_education_initial_state,
            next_unwritten_topic,
        )
        from app.modules.llm.qdb_callback import QDBCostCallback

        # Find which topics already have stored explainers
        import os, requests as req
        host = os.getenv("QUESTDB_HOST", "questdb")
        written: set[str] = set()
        try:
            resp = req.get(
                f"http://{host}:9000/exec",
                params={"query": "SELECT slug FROM technical_explainers"},
                timeout=5,
            )
            written = {row[0] for row in resp.json().get("dataset", [])}
        except Exception:
            pass

        slug = next_unwritten_topic(written)
        if not slug:
            log.info("archive_node pass3: all education topics already written")
            return

        alias = state.get("model_aliases", {}).get("archive", "sonnet")
        graph  = build_education_graph()
        init   = make_education_initial_state(topic_slug=slug, model_alias=alias)
        config = RunnableConfig(callbacks=[QDBCostCallback(agent_name="archive_education")])
        result = graph.invoke(init, config=config)
        if result.get("errors"):
            log.warning("archive_node pass3 (education) errors: %s", result["errors"])
        else:
            log.info("archive_node pass3: wrote explainer for %r", slug)
    except Exception as exc:
        log.error("archive_node pass3 (education) failed: %s", exc)


def archive_node(state: ArchiveGraphState) -> dict:
    if state.get("dry_run"):
        log.info("archive_node: dry_run — skipping all LLM calls")
        return {"archive_report": None}

    since = state.get("last_archive_date", "2026-01-01")
    alias = state.get("model_aliases", {}).get("archive", "sonnet")
    llm   = get_agent_model("archive", override=alias)

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
        existing  = _extract_existing_glossary_terms()
        new_terms = _discover_new_terms(since)
        if new_terms:
            glossary_updates = llm.with_structured_output(list[GlossaryEntry]).invoke(
                build_glossary_prompt(existing, new_terms)
            )
            log.info("archive_node pass2: %d glossary entries", len(glossary_updates))
    except Exception as exc:
        log.error("archive_node pass2 (glossary) failed: %s", exc)
        errors.append(f"glossary: {exc}")

    # Pass 3: delegate to education_graph (separate LangSmith trace, separate node)
    _run_education_pass(state)

    # Pass 4: performance summary (code only)
    perf = _read_performance_data(since)

    report = ArchiveReport(
        generated_at=datetime.now(timezone.utc).isoformat(),
        milestones=milestones,
        glossary_updates=glossary_updates,
        technical_explainers=[],    # now owned by education_graph
        performance_summary=perf,
        next_focus="see /explain/topics",
    )

    return {"archive_report": report.model_dump(), "errors": errors}
