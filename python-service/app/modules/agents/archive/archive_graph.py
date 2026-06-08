"""
build_archive_graph() — separate LangGraph StateGraph for the archive/historian pipeline.

No shared state with the analysis graph. Runs weekly (Sunday 00:00 ET)
and on milestone-triggered Prefect deployments.

Topology: START → archive_node → persist_archive_node → END
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from langgraph.graph import END, START, StateGraph

from app.modules.agents.archive.state import ArchiveGraphState
from app.modules.agents.archive.nodes.archive_node import archive_node

log = logging.getLogger(__name__)

QDB_CONF = os.getenv("QDB_CLIENT_CONF", "http::addr=questdb:9000;")


def persist_archive_node(state: ArchiveGraphState) -> dict:
    """Write archive_report to QuestDB tables."""
    report = state.get("archive_report")
    if not report:
        return {}
    try:
        from questdb.ingress import Sender, TimestampNanos
        perf = report.get("performance_summary", {})
        with Sender.from_conf(QDB_CONF) as sender:
            sender.row(
                "archive_reports",
                symbols={},
                columns={
                    "period_start":    perf.get("period", "").split(" to ")[0],
                    "period_end":      perf.get("period", "").split(" to ")[-1],
                    "signals_flagged": int(perf.get("signals_flagged", 0)),
                    "avg_conviction":  float(perf.get("avg_conviction_score", 0)),
                    "outcomes_avail":  bool(perf.get("outcomes_available", False)),
                    "narrative":       perf.get("narrative", ""),
                    "next_focus":      report.get("next_focus", ""),
                },
                at=TimestampNanos.now(),
            )
            for m in report.get("milestones", []):
                sender.row(
                    "project_milestones",
                    symbols={"model_id": "archive"},
                    columns={
                        "event_date":       m.get("date", ""),
                        "title":            m.get("title", ""),
                        "description":      m.get("description", ""),
                        "technical_detail": m.get("technical_detail", ""),
                        "impact":           m.get("impact", ""),
                    },
                    at=TimestampNanos.now(),
                )
            for e in report.get("technical_explainers", []):
                sender.row(
                    "technical_explainers",
                    symbols={"topic": e.get("topic", ""), "model_id": "archive_deep"},
                    columns={
                        "body":           e.get("body", ""),
                        "key_invariants": str(e.get("key_invariants", [])),
                        "gotchas":        str(e.get("gotchas", [])),
                    },
                    at=TimestampNanos.now(),
                )
            sender.flush()
        log.info("persist_archive_node: wrote report + %d milestones + %d explainers",
                 len(report.get("milestones", [])),
                 len(report.get("technical_explainers", [])))
    except Exception as exc:
        log.error("persist_archive_node write failed: %s", exc)
    return {}


def build_archive_graph(checkpointer=None):
    graph = StateGraph(ArchiveGraphState)
    graph.add_node("archive_node",        archive_node)
    graph.add_node("persist_archive_node", persist_archive_node)
    graph.add_edge(START, "archive_node")
    graph.add_edge("archive_node", "persist_archive_node")
    graph.add_edge("persist_archive_node", END)

    compile_kwargs = {}
    if checkpointer is not None:
        compile_kwargs["checkpointer"] = checkpointer
    return graph.compile(**compile_kwargs)


def make_archive_initial_state(
    last_archive_date: str | None = None,
    model_aliases: dict[str, str] | None = None,
    dry_run: bool = False,
) -> dict:
    return {
        "last_archive_date": last_archive_date or "2026-01-01",
        "model_aliases":     model_aliases or {},
        "dry_run":           dry_run,
        "git_log":           "",
        "worklog":           "",
        "archive_report":    None,
        "errors":            [],
    }
