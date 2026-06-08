"""persist_explainer_node — writes the TechnicalExplainer to QuestDB."""
from __future__ import annotations

import logging
import os

from app.modules.agents.education.state import EducationGraphState

log = logging.getLogger(__name__)

QDB_CONF = os.getenv("QDB_CLIENT_CONF", "http::addr=questdb:9000;")


def persist_explainer_node(state: EducationGraphState) -> dict:
    explainer = state.get("explainer")
    if not explainer:
        log.info("persist_explainer_node: nothing to write (explainer is None)")
        return {}
    try:
        from questdb.ingress import Sender, TimestampNanos
        with Sender.from_conf(QDB_CONF) as sender:
            sender.row(
                "technical_explainers",
                symbols={
                    "topic":    explainer.get("topic", state.get("topic_slug", "")),
                    "category": state.get("topic_category", ""),
                    "model_id": state.get("model_alias", "sonnet"),
                    "slug":     state.get("topic_slug", ""),
                },
                columns={
                    "audience":       explainer.get("audience", ""),
                    "body":           explainer.get("body", ""),
                    "key_invariants": str(explainer.get("key_invariants", [])),
                    "gotchas":        str(explainer.get("gotchas", [])),
                },
                at=TimestampNanos.now(),
            )
            sender.flush()
        log.info("persist_explainer_node: wrote explainer for %r", explainer.get("topic"))
    except Exception as exc:
        log.error("persist_explainer_node write failed: %s", exc)
    return {}
