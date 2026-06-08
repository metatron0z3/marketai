"""
build_education_graph() — standalone LangGraph StateGraph for on-demand explainers.

Topology: START → load_context_node → explainer_node → persist_explainer_node → END

Triggered:
  - On demand: POST /api/v1/archive/explain?slug=<topic_slug>
  - By archive_flow when it detects topics with no stored explainer
  - Future: Angular /docs sidebar "Generate" button

Completely separate from the analysis graph — different state, different schedule,
different Prefect flow. One run = one topic.
"""
from __future__ import annotations

import os

from langgraph.graph import END, START, StateGraph

from app.modules.agents.education.state import EducationGraphState
from app.modules.agents.education.nodes.load_context_node  import load_context_node
from app.modules.agents.education.nodes.explainer_node     import explainer_node
from app.modules.agents.education.nodes.persist_explainer_node import persist_explainer_node

_DEFAULT_ALIAS = os.getenv("EDUCATION_MODEL", "sonnet")


def build_education_graph(checkpointer=None):
    graph = StateGraph(EducationGraphState)

    graph.add_node("load_context_node",     load_context_node)
    graph.add_node("explainer_node",        explainer_node)
    graph.add_node("persist_explainer_node", persist_explainer_node)

    graph.add_edge(START,                   "load_context_node")
    graph.add_edge("load_context_node",     "explainer_node")
    graph.add_edge("explainer_node",        "persist_explainer_node")
    graph.add_edge("persist_explainer_node", END)

    compile_kwargs = {}
    if checkpointer is not None:
        compile_kwargs["checkpointer"] = checkpointer
    return graph.compile(**compile_kwargs)


def make_education_initial_state(
    topic_slug: str,
    model_alias: str | None = None,
    dry_run: bool = False,
) -> dict:
    return {
        "topic_slug":        topic_slug,
        "model_alias":       model_alias or _DEFAULT_ALIAS,
        "dry_run":           dry_run,
        "topic_title":       "",
        "topic_category":    "",
        "topic_description": "",
        "source_snippets":   {},
        "explainer":         None,
        "errors":            [],
    }


def list_topics() -> list[dict]:
    """Return the full topic registry as a list of dicts for the API."""
    from app.modules.agents.education.topics import TOPIC_REGISTRY
    return [
        {
            "slug":        slug,
            "title":       meta["title"],
            "category":    meta["category"],
            "description": meta["description"],
        }
        for slug, meta in TOPIC_REGISTRY.items()
    ]


def next_unwritten_topic(written_slugs: set[str]) -> str | None:
    """Return the first TOPIC_ORDER slug not yet in written_slugs."""
    from app.modules.agents.education.topics import TOPIC_ORDER
    for slug in TOPIC_ORDER:
        if slug not in written_slugs:
            return slug
    return None
