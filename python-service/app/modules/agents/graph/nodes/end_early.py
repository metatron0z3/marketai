"""end_early_node — logs accumulated errors and exits the graph cleanly."""
from __future__ import annotations

import logging

from app.modules.agents.graph.state import GraphState

log = logging.getLogger(__name__)


def end_early_node(state: GraphState) -> dict:
    for err in state.get("errors", []):
        log.error("Graph ended early: %s", err)
    log.info("end_early_node: graph terminated before LLM nodes")
    return {}
