"""
load_context_node — code-only node.

Reads the topic metadata and the actual source files from disk so the
explainer_node has real code context rather than just a topic string.
Source files are truncated to 3 000 chars each to stay within context limits.
"""
from __future__ import annotations

import logging
from pathlib import Path

from app.modules.agents.education.state import EducationGraphState
from app.modules.agents.education.topics import TOPIC_REGISTRY

log = logging.getLogger(__name__)

# python-service/ is 2 levels up from nodes/
_PYTHON_SERVICE = Path(__file__).parents[5]
_MAX_SNIPPET    = 3_000   # chars per source file


def load_context_node(state: EducationGraphState) -> dict:
    slug = state["topic_slug"]
    if slug not in TOPIC_REGISTRY:
        return {
            "errors": [f"Unknown topic slug: {slug!r}. "
                       f"Available: {list(TOPIC_REGISTRY)[:5]}..."],
        }

    meta = TOPIC_REGISTRY[slug]
    snippets: dict[str, str] = {}

    for rel_path in meta.get("source_files", []):
        full = _PYTHON_SERVICE / rel_path
        try:
            text = full.read_text(encoding="utf-8")
            snippets[rel_path] = text[:_MAX_SNIPPET] + ("…" if len(text) > _MAX_SNIPPET else "")
            log.debug("load_context_node: loaded %s (%d chars)", rel_path, len(text))
        except FileNotFoundError:
            log.warning("load_context_node: source file not found: %s", full)
        except Exception as exc:
            log.warning("load_context_node: could not read %s: %s", rel_path, exc)

    return {
        "topic_title":       meta["title"],
        "topic_category":    meta["category"],
        "topic_description": meta["description"],
        "source_snippets":   snippets,
        "errors":            [],
    }
