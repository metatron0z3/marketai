"""EducationGraphState — standalone state for on-demand explainer generation."""
from __future__ import annotations

from typing_extensions import TypedDict


class EducationGraphState(TypedDict):
    # ── Inputs ────────────────────────────────────────────────────────────
    topic_slug:    str              # key in TOPIC_REGISTRY
    model_alias:   str              # defaults to EDUCATION_MODEL env var
    dry_run:       bool

    # ── Derived (populated by load_context_node) ──────────────────────────
    topic_title:       str
    topic_category:    str
    topic_description: str
    source_snippets:   dict[str, str]   # filename → file content

    # ── LLM output (populated by explainer_node) ──────────────────────────
    explainer: dict | None

    # ── Errors ────────────────────────────────────────────────────────────
    errors: list[str]
