"""
QDBCostCallback — LangChain BaseCallbackHandler that writes LLM call cost
to the llm_audit_log QuestDB table after every LangGraph node invocation.

LangSmith already traces everything via LANGCHAIN_TRACING_V2=true.
This callback fills the one gap: budget_guard reads from llm_audit_log (QuestDB)
to enforce daily/monthly caps. LangSmith doesn't write there.

Attach to any LangGraph node via RunnableConfig:
    config = RunnableConfig(callbacks=[QDBCostCallback(agent_name="research_node")])
    llm.with_structured_output(Model).invoke(messages, config=config)

Fire-and-forget: a write failure never breaks the LLM call.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

log = logging.getLogger(__name__)

QDB_CONF = os.getenv("QDB_CLIENT_CONF", "http::addr=questdb:9000;")


class QDBCostCallback(BaseCallbackHandler):
    """Write per-call token counts and cost to llm_audit_log after every LLM call."""

    def __init__(self, agent_name: str = "graph_node", symbol: str = "") -> None:
        super().__init__()
        self.agent_name  = agent_name
        self.symbol      = symbol
        self._start_time = 0.0

    def on_llm_start(self, serialized: dict[str, Any], prompts: list[str], **kwargs) -> None:
        self._start_time = time.monotonic()

    def on_llm_end(self, response: LLMResult, **kwargs) -> None:
        try:
            self._write(response)
        except Exception as exc:
            log.warning("QDBCostCallback write failed (non-fatal): %s", exc)

    def _write(self, response: LLMResult) -> None:
        from app.modules.llm.cost_tracker import compute_cost

        llm_output  = response.llm_output or {}
        model_id    = llm_output.get("model_name") or llm_output.get("model", "unknown")
        usage       = llm_output.get("token_usage") or llm_output.get("usage", {})

        input_toks  = int(usage.get("prompt_tokens",     usage.get("input_tokens",  0)))
        output_toks = int(usage.get("completion_tokens", usage.get("output_tokens", 0)))
        latency_ms  = int((time.monotonic() - self._start_time) * 1000)

        # Determine provider from model_id prefix
        if model_id.startswith("claude"):
            provider = "anthropic"
        elif model_id.startswith(("gpt-", "o1", "o3")):
            provider = "openai"
        elif model_id.startswith("gemini"):
            provider = "gemini"
        elif model_id.startswith("deepseek"):
            provider = "deepseek"
        else:
            provider = "ollama"

        try:
            cost = compute_cost(model_id, input_toks, output_toks)
            cost_usd = cost.cost_usd
        except Exception:
            cost_usd = 0.0

        from questdb.ingress import Sender, TimestampNanos
        with Sender.from_conf(QDB_CONF) as sender:
            sender.row(
                "llm_audit_log",
                symbols={
                    "agent_name":  self.agent_name,
                    "provider":    provider,
                    "model_id":    model_id,
                    "symbol":      self.symbol,
                    "status":      "ok",
                },
                columns={
                    "input_tokens":  input_toks,
                    "output_tokens": output_toks,
                    "cost_usd":      cost_usd,
                    "latency_ms":    latency_ms,
                },
                at=TimestampNanos.now(),
            )
            sender.flush()

        log.debug(
            "QDBCostCallback: %s model=%s in=%d out=%d cost=$%.6f latency=%dms",
            self.agent_name, model_id, input_toks, output_toks, cost_usd, latency_ms,
        )
