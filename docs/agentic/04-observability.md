# Phase 4 — Observability: LangSmith, Cost Tracking, Alerts

## Goal

Wire LangSmith as the primary observability layer for all LangGraph executions.
Add cost callbacks to surface per-node and per-run spend in both LangSmith and
the existing `llm_audit_log` QuestDB table (for budget enforcement).
Define alert thresholds so the daily brief surfaces degraded model calls.

---

## 4.1 — What LangSmith Gives You (for free)

Once `LANGCHAIN_TRACING_V2=true` and `LANGCHAIN_API_KEY` are set, every
LangGraph `.invoke()` or `.astream()` call is automatically traced.

### Per-node trace data

| Field | Source | Available in LangSmith UI |
|---|---|---|
| Node name | Graph topology | ✅ |
| Full prompt sent | `BaseChatModel` | ✅ |
| Full LLM response | `BaseChatModel` | ✅ |
| Input tokens | Provider usage API | ✅ |
| Output tokens | Provider usage API | ✅ |
| Latency (ms) | Instrumented | ✅ |
| Model ID + provider | `BaseChatModel` | ✅ |
| Error + traceback | Automatic | ✅ |

### Per-run trace data

| Field | Available |
|---|---|
| Full graph execution path (which edges were taken) | ✅ |
| Which conditional edge fired | ✅ |
| Fan-out executions (each Send creates a child trace) | ✅ |
| Total token count across all nodes | ✅ |
| Wall-clock time for full graph | ✅ |
| Cost estimate (LangSmith computes from token counts) | ✅ |

No custom audit code is needed for any of the above.

---

## 4.2 — Adding Metadata to Traces

LangSmith lets you attach custom metadata to traces. Use this to make
the trace searchable by ticker, target_date, conviction score, etc.

### Option A — `RunnableConfig` (per-invoke)

```python
from langchain_core.runnables import RunnableConfig

config = RunnableConfig(
    tags=["production", "options-analysis"],
    metadata={
        "target_date":  state["target_date"],
        "symbols":      state["symbols"],
        "total_flagged": state["total_flagged"],
    },
    run_name="options-analysis-2026-06-07",
)

result = graph.invoke(state, config=config)
```

### Option B — Tracing context inside a node

```python
from langsmith import traceable

@traceable(name="research_node", tags=["llm", "research"])
def research_node(state: GraphState) -> dict:
    ...
```

Use `@traceable` on any helper function you want to appear as a child span
in the trace (e.g. `_run_sector_contagion`, `_run_gamma_squeeze`).

---

## 4.3 — Cost Callback (QuestDB Bridge)

LangSmith records costs in its own UI. We also need to feed them into the
existing `llm_audit_log` QuestDB table for the `budget_guard` to enforce
daily/monthly caps.

**File**: `python-service/app/modules/llm/langsmith_callback.py`

```python
"""
LangSmith → QuestDB bridge callback.

Registers as a LangChain callback handler. After every LLM call, writes
to llm_audit_log so budget_guard can enforce daily/monthly caps.

Usage:
    from app.modules.llm.langsmith_callback import QDBCostCallback
    config = RunnableConfig(callbacks=[QDBCostCallback(caller="research_node", symbol="NVDA")])
    llm.invoke(prompt, config=config)
"""
from __future__ import annotations
import logging
import os
import time
from typing import Any
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler

log = logging.getLogger(__name__)


class QDBCostCallback(BaseCallbackHandler):
    """
    After each LLM call, compute cost from token usage and write to llm_audit_log.
    Compatible with any BaseChatModel provider.
    """

    def __init__(self, caller: str, symbol: str = "") -> None:
        self.caller = caller
        self.symbol = symbol
        self._start: dict[UUID, float] = {}

    def on_llm_start(self, serialized: dict, prompts: list[str], *, run_id: UUID, **_) -> None:
        self._start[run_id] = time.monotonic()

    def on_llm_end(self, response, *, run_id: UUID, **kwargs) -> None:
        from app.modules.llm.cost_tracker import compute_cost

        latency_ms = int((time.monotonic() - self._start.pop(run_id, time.monotonic())) * 1000)
        usage = getattr(response, "llm_output", {}) or {}

        # Token counts — location differs by provider
        input_tokens  = (
            usage.get("token_usage", {}).get("prompt_tokens") or
            usage.get("usage", {}).get("input_tokens") or
            0
        )
        output_tokens = (
            usage.get("token_usage", {}).get("completion_tokens") or
            usage.get("usage", {}).get("output_tokens") or
            0
        )
        model_id = (
            usage.get("model_name") or
            usage.get("model") or
            "unknown"
        )

        try:
            cost = compute_cost(model_id, input_tokens, output_tokens)
            _write_audit_log(
                caller=self.caller,
                model=model_id,
                symbol=self.symbol,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost.cost_usd,
                latency_ms=latency_ms,
                status="ok",
            )
        except Exception as exc:
            log.warning("QDBCostCallback write failed: %s", exc)

    def on_llm_error(self, error: Exception, *, run_id: UUID, **kwargs) -> None:
        latency_ms = int((time.monotonic() - self._start.pop(run_id, time.monotonic())) * 1000)
        _write_audit_log(
            caller=self.caller, model="unknown", symbol=self.symbol,
            input_tokens=0, output_tokens=0, cost_usd=0.0,
            latency_ms=latency_ms, status="error",
            error_msg=str(error)[:512],
        )


def _write_audit_log(
    caller: str, model: str, symbol: str,
    input_tokens: int, output_tokens: int, cost_usd: float,
    latency_ms: int, status: str, error_msg: str = "",
) -> None:
    try:
        from questdb.ingress import Sender, TimestampNanos
        conf = os.getenv("QDB_CLIENT_CONF", "http::addr=questdb:9000;")
        with Sender.from_conf(conf) as sender:
            sender.row(
                "llm_audit_log",
                symbols={"caller": caller, "model": model, "symbol": symbol, "status": status},
                columns={
                    "prompt_tokens":     input_tokens,
                    "completion_tokens": output_tokens,
                    "cost_usd":          cost_usd,
                    "latency_ms":        latency_ms,
                    "error_msg":         error_msg,
                    "provider":          _provider_from_model(model),
                },
                at=TimestampNanos.now(),
            )
            sender.flush()
    except Exception as exc:
        log.warning("llm_audit_log write failed: %s", exc)


def _provider_from_model(model_id: str) -> str:
    if "claude" in model_id:   return "anthropic"
    if "gpt" in model_id:      return "openai"
    if "deepseek" in model_id: return "deepseek"
    if "gemini" in model_id:   return "gemini"
    return "unknown"
```

### Attaching to a node

```python
from app.modules.llm.langsmith_callback import QDBCostCallback

def research_node(state: GraphState) -> dict:
    alias  = state["model_aliases"].get("research", "sonnet")
    llm    = get_agent_model("research", override=alias)
    config = RunnableConfig(callbacks=[QDBCostCallback("research_node")])

    result = llm.with_structured_output(ResearchContext).invoke(prompt, config=config)
    return {"research_context": result.model_dump()}
```

---

## 4.4 — Cost Tracking Table: `cost_tracker.py` Additions

Add DeepSeek to the existing pricing table in `llm/cost_tracker.py`:

```python
PRICING: dict[str, dict] = {
    # ... existing Anthropic models ...
    "claude-haiku-4-5-20251001": {"input": 0.80,  "output": 4.00},
    "claude-sonnet-4-6":         {"input": 3.00,  "output": 15.00},
    "claude-opus-4-8":           {"input": 15.00, "output": 75.00},

    # OpenAI
    "gpt-4o-mini":               {"input": 0.15,  "output": 0.60},
    "gpt-4o":                    {"input": 2.50,  "output": 10.00},

    # Gemini
    "gemini-2.0-flash":          {"input": 0.10,  "output": 0.40},
    "gemini-2.5-pro":            {"input": 1.25,  "output": 10.00},

    # DeepSeek (prices per million tokens, as of 2026)
    "deepseek-chat":             {"input": 0.07,  "output": 1.10},
    "deepseek-reasoner":         {"input": 0.55,  "output": 2.19},

    # Ollama — zero cost (local)
    "llama3.3:70b":              {"input": 0.0,   "output": 0.0},
    "mistral:7b":                {"input": 0.0,   "output": 0.0},
}
```

---

## 4.5 — LangSmith Alerting

LangSmith supports rules-based alerts (email/Slack webhook) at `smith.langchain.com/alerts`.

### Recommended alert rules

| Alert | Condition | Action |
|---|---|---|
| High latency | Any node `latency_ms > 30_000` (30s) | Slack webhook |
| LLM error rate | >2 errors in 10-minute window | Slack webhook |
| Daily cost spike | Run cost > $1.00 (vs $0.27 avg) | Email |
| Structured output failure | `on_llm_error` fired by `with_structured_output` | Slack |
| Budget gate firing | `budget_ok=False` tag on trace | Email |

### Custom LangSmith tags for filtering

Add these tags to every graph invocation config:

```python
tags = [
    "env:production",          # or "env:development"
    f"date:{state['target_date']}",
    f"symbols:{'-'.join(state['symbols'][:3])}",
    f"model:{state['model_aliases'].get('research','sonnet')}",
]
```

---

## 4.6 — Observability Dashboard in Angular

Surface key LangGraph run metrics in the existing Angular frontend
via new NestJS proxy endpoints:

```
GET /api/v1/agents/run-log       → agent_run_log (QuestDB)
GET /api/v1/agents/brief/{date}  → daily_briefs (QuestDB)
GET /api/v1/agents/cost/daily    → daily cost summary from llm_audit_log
```

The Angular Data Overview page (already built) can add an "Agent Runs" tile
showing: runs today, flagged signals, cost, model used, LangSmith link.

---

## Phase 4 Deliverables

- [ ] `llm/langsmith_callback.py` — `QDBCostCallback` BaseCallbackHandler
- [ ] `llm/cost_tracker.py` — add DeepSeek + Gemini + Ollama pricing rows
- [ ] LangSmith project configured, alert rules set (latency, error rate, cost)
- [ ] `RunnableConfig` with tags + metadata wired into every LLM node
- [ ] Angular "Agent Runs" tile (stretch goal — defer to Phase 5 if time constrained)

## Commit checkpoint

```
feat(agents/phase4): LangSmith callback bridge → QDB, DeepSeek pricing, alert config
```
