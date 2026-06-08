"""
BaseAgent — shared interface for all multi-agent pipeline agents.

All agents:
- Accept a model_alias override (defaults to env var, then built-in default)
- Are idempotent (check existing results before making LLM calls)
- Are budget-aware (raise BudgetExceededError if budget is exhausted)
- Return typed dicts (parse JSON from LLM text, never return raw strings)
- Log every LLM call to agent_run_log via _log_run()
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

log = logging.getLogger(__name__)


@dataclass
class AgentContext:
    run_id: str
    target_date: str
    symbols: list[str]
    budget_remaining_usd: float
    metadata: dict = field(default_factory=dict)


class BaseAgent(ABC):
    """
    Subclass this and implement run(). Call self._llm() for any LLM inference.
    The name and default_model_alias class attributes must be set on each subclass.
    """

    name: str = "base"
    default_model_alias: str = "sonnet"

    def __init__(self, model_alias: str | None = None) -> None:
        from app.modules.llm.model_registry import resolve_agent_alias
        self.model_alias = resolve_agent_alias(self.name, override=model_alias)

    @abstractmethod
    def run(self, ctx: AgentContext, **inputs) -> dict: ...

    # ------------------------------------------------------------------
    # LLM helper — routes through model registry, logs to agent_run_log
    # ------------------------------------------------------------------

    def _llm(
        self,
        messages: list[dict],
        system: str | None = None,
        max_tokens: int = 500,
        temperature: float = 0.0,
        symbol: str | None = None,
    ) -> str:
        from app.modules.llm.model_registry import get_backend
        from app.modules.llm.budget_guard import BudgetExceededError, check_budget

        try:
            check_budget()
        except BudgetExceededError:
            log.error("%s: budget exceeded — skipping LLM call", self.name)
            raise

        backend, model_id = get_backend(self.model_alias)
        resp = backend.complete(
            messages=messages,
            model=model_id,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system,
        )

        self._log_run(resp, symbol=symbol)
        return resp.text

    # ------------------------------------------------------------------
    # JSON parsing helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_json(text: str) -> dict:
        """Extract the first JSON object from LLM text output."""
        text = text.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            m = re.search(r'\{.*\}', text, re.DOTALL)
            if m:
                return json.loads(m.group())
            raise ValueError(f"No valid JSON found in LLM response: {text[:300]}")

    @staticmethod
    def _parse_json_list(text: str) -> list:
        text = text.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            m = re.search(r'\[.*\]', text, re.DOTALL)
            if m:
                return json.loads(m.group())
            raise ValueError(f"No valid JSON array in LLM response: {text[:300]}")

    # ------------------------------------------------------------------
    # Audit log
    # ------------------------------------------------------------------

    def _log_run(self, resp, symbol: str | None = None) -> None:
        from app.modules.llm.cost_tracker import compute_cost
        try:
            cost = compute_cost(resp.model, resp.input_tokens, resp.output_tokens)
            _write_agent_run_log(
                agent_name=self.name,
                model_alias=self.model_alias,
                provider=resp.provider,
                model_id=resp.model,
                symbol=symbol or "",
                input_tokens=resp.input_tokens,
                output_tokens=resp.output_tokens,
                cost_usd=cost.cost_usd,
                latency_ms=resp.latency_ms,
                status="ok",
            )
        except Exception as exc:
            log.warning("agent_run_log write failed: %s", exc)


# ---------------------------------------------------------------------------
# QuestDB writer for agent_run_log
# ---------------------------------------------------------------------------

def _write_agent_run_log(
    agent_name: str,
    model_alias: str,
    provider: str,
    model_id: str,
    symbol: str,
    input_tokens: int,
    output_tokens: int,
    cost_usd: float,
    latency_ms: int,
    status: str,
    error_msg: str = "",
    flow_run_id: str = "",
) -> None:
    try:
        from questdb.ingress import Sender, TimestampNanos
        conf = os.getenv("QDB_CLIENT_CONF", "http::addr=questdb:9000;")
        with Sender.from_conf(conf) as sender:
            sender.row(
                "agent_run_log",
                symbols={
                    "agent_name":  agent_name,
                    "model_alias": model_alias,
                    "provider":    provider,
                    "model_id":    model_id,
                    "symbol":      symbol,
                    "status":      status,
                },
                columns={
                    "flow_run_id":   flow_run_id,
                    "input_tokens":  input_tokens,
                    "output_tokens": output_tokens,
                    "cost_usd":      cost_usd,
                    "latency_ms":    latency_ms,
                    "error_msg":     error_msg,
                },
                at=TimestampNanos.now(),
            )
            sender.flush()
    except Exception as exc:
        log.warning("agent_run_log QDB write failed: %s", exc)
