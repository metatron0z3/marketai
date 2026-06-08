"""
ArchiveGraphState — separate TypedDict for the archive/historian pipeline.

No shared state with the analysis graph. Different Prefect flow, different
schedule (weekly Sunday 00:00 ET + milestone-triggered).
"""
from __future__ import annotations

from typing_extensions import TypedDict


class ArchiveGraphState(TypedDict):
    # ── Inputs ────────────────────────────────────────────────────────────
    last_archive_date: str          # ISO date — read git log / glossary since this date
    model_aliases: dict[str, str]   # {"archive": "sonnet", "archive_deep": "opus"}
    dry_run: bool

    # ── Git + docs context (populated by archive_node) ───────────────────
    git_log: str
    worklog: str

    # ── LLM outputs ──────────────────────────────────────────────────────
    archive_report: dict | None

    # ── Errors ────────────────────────────────────────────────────────────
    errors: list[str]
