"""
explainer_node — 1 LLM call per topic.

Reads topic metadata + source snippets from state, builds a targeted prompt,
and returns a TechnicalExplainer Pydantic model via structured output.

System prompt is tuned for the target audience: programmer who knows how to
code but is new to LangGraph, Prefect, and ML — so analogies to familiar
patterns (for-loops, dictionaries, function calls) are preferred.
"""
from __future__ import annotations

import json
import logging
import os

from langchain_core.messages import HumanMessage, SystemMessage

from app.modules.agents.education.state import EducationGraphState
from app.modules.agents.graph.models import TechnicalExplainer
from app.modules.llm.model_factory import build_chat_model

log = logging.getLogger(__name__)

_DEFAULT_ALIAS = os.getenv("EDUCATION_MODEL", "sonnet")

_SYSTEM = """\
You are writing technical documentation for an experienced programmer who is \
new to machine learning, LangGraph, and Prefect. They are comfortable reading \
Python code. They are NOT familiar with ML jargon, graph frameworks, or \
quantitative finance.

Your writing style:
- Use concrete examples with real numbers or real variable names from the code.
- When introducing jargon, define it immediately on first use.
- Prefer analogies to familiar programming concepts (loops, dicts, function calls).
- Do not assume the reader knows what a "node", "tensor", "epoch", or "Kelly" is.
- body is 4–7 paragraphs of markdown. Use ## subheadings to break it up.
- key_invariants are things that must remain true for the code to work — \
  things a future developer must NOT break.
- gotchas are non-obvious failure modes or surprising behaviour. \
  At least 2, at most 5.

Return ONLY valid structured output matching the TechnicalExplainer schema. \
Never add explanations outside the schema fields.\
"""


def explainer_node(state: EducationGraphState) -> dict:
    if state.get("dry_run"):
        log.info("explainer_node: dry_run — skipping LLM call for %r", state.get("topic_slug"))
        return {"explainer": {
            "topic":          state.get("topic_title", state.get("topic_slug", "")),
            "audience":       "dry_run",
            "body":           "dry_run — no LLM call made",
            "key_invariants": [],
            "gotchas":        [],
        }}

    alias = state.get("model_alias") or _DEFAULT_ALIAS
    context = {
        "topic":       state["topic_title"],
        "category":    state["topic_category"],
        "description": state["topic_description"],
        "code_snippets": state.get("source_snippets") or {},
    }

    messages = [
        SystemMessage(content=_SYSTEM),
        HumanMessage(content=(
            f"CONTEXT:\n{json.dumps(context, default=str)}\n\n"
            f"Produce a TechnicalExplainer for: {state['topic_title']}\n\n"
            f"Fields required: topic (str), audience (str), body (markdown, 4-7 paragraphs), "
            f"key_invariants (list[str], 2-5 items), gotchas (list[str], 2-5 items)."
        )),
    ]

    llm = build_chat_model(alias)
    try:
        result: TechnicalExplainer = (
            llm.with_structured_output(TechnicalExplainer).invoke(messages)
        )
        log.info("explainer_node: wrote explainer for %r (%d chars body)",
                 result.topic, len(result.body))
        return {"explainer": result.model_dump()}
    except Exception as exc:
        log.error("explainer_node LLM call failed for %r: %s", state.get("topic_slug"), exc)
        return {
            "explainer": None,
            "errors": [f"explainer_node {state.get('topic_slug', '?')}: {exc}"],
        }
