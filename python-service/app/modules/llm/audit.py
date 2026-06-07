"""
LLM call auditor — wraps anthropic.Anthropic.messages.create() and writes
every call to llm_audit_log in QuestDB.  All LLM code in this project should
route through LLMClient rather than calling the Anthropic SDK directly.

Usage:
    from app.modules.llm.audit import LLMClient

    client = LLMClient(caller="options_enrichment", symbol="TSLA")
    result = client.create(
        model="claude-haiku-4-5",
        max_tokens=256,
        messages=[{"role": "user", "content": "..."}],
    )
    text = result.content[0].text
    cost = result.audit.cost_usd          # available on the extended response
"""
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger(__name__)


@dataclass
class AuditedResponse:
    """anthropic.Message + audit fields."""
    raw: Any                              # the original anthropic.Message object
    audit: "AuditRecord"

    # delegate common attribute access to the underlying message
    def __getattr__(self, name: str):
        return getattr(self.raw, name)


@dataclass
class AuditRecord:
    caller: str
    model: str
    symbol: str | None
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float
    latency_ms: int
    status: str               # "ok" | "error"
    error_msg: str = ""
    flow_run_id: str = field(default_factory=lambda: _get_flow_run_id())


def _get_flow_run_id() -> str:
    try:
        from prefect.runtime import flow_run
        return str(flow_run.id) if flow_run.id else ""
    except Exception:
        return ""


class LLMClient:
    """
    Thin wrapper around anthropic.Anthropic that logs every call to QuestDB.

    Args:
        caller: logical name of the calling module (e.g. "options_enrichment")
        symbol: ticker being processed, if applicable
    """

    def __init__(self, caller: str, symbol: str | None = None):
        self.caller = caller
        self.symbol = symbol or ""
        self._client = None

    def _get_client(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        return self._client

    def create(self, **kwargs) -> AuditedResponse:
        """
        Call messages.create() and automatically log the result to llm_audit_log.
        Accepts the same keyword arguments as anthropic.Anthropic.messages.create().
        """
        from app.modules.llm.cost_tracker import compute_cost

        model = kwargs.get("model", "claude-haiku-4-5")
        t0 = time.monotonic()
        status = "ok"
        error_msg = ""
        raw = None

        try:
            raw = self._get_client().messages.create(**kwargs)
            usage = raw.usage
            prompt_tokens     = usage.input_tokens
            completion_tokens = usage.output_tokens
        except Exception as exc:
            latency_ms = int((time.monotonic() - t0) * 1000)
            status     = "error"
            error_msg  = str(exc)[:512]
            record = AuditRecord(
                caller=self.caller, model=model, symbol=self.symbol,
                prompt_tokens=0, completion_tokens=0, cost_usd=0.0,
                latency_ms=latency_ms, status=status, error_msg=error_msg,
            )
            self._write_audit(record)
            raise

        latency_ms = int((time.monotonic() - t0) * 1000)
        cost_rec   = compute_cost(model, prompt_tokens, completion_tokens)
        record = AuditRecord(
            caller=self.caller, model=model, symbol=self.symbol,
            prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
            cost_usd=cost_rec.cost_usd, latency_ms=latency_ms, status=status,
        )
        self._write_audit(record)

        log.debug(
            "%s → %s: %d+%d tokens = $%.6f (%.0fms)",
            self.caller, model, prompt_tokens, completion_tokens,
            cost_rec.cost_usd, latency_ms,
        )

        return AuditedResponse(raw=raw, audit=record)

    def _write_audit(self, record: AuditRecord) -> None:
        """Fire-and-forget write to llm_audit_log via QuestDB ILP."""
        try:
            from datetime import datetime, timezone
            from questdb.ingress import Sender, TimestampNanos

            conf = os.getenv("QDB_CLIENT_CONF", "http::addr=questdb:9000;")
            with Sender.from_conf(conf) as sender:
                sender.row(
                    "llm_audit_log",
                    symbols={
                        "caller":  record.caller,
                        "model":   record.model,
                        "symbol":  record.symbol,
                        "status":  record.status,
                    },
                    columns={
                        "prompt_tokens":     record.prompt_tokens,
                        "completion_tokens": record.completion_tokens,
                        "cost_usd":          record.cost_usd,
                        "latency_ms":        record.latency_ms,
                        "error_msg":         record.error_msg,
                        "flow_run_id":       record.flow_run_id,
                    },
                    at=TimestampNanos.now(),
                )
                sender.flush()
        except Exception as exc:
            # never let audit failure break the caller
            log.warning("llm_audit_log write failed: %s", exc)
