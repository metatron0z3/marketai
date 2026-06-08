# Phase 5 — Deployment: Docker, Prefect, FastAPI, Migration

## Goal

Wire the LangGraph graph into the existing infrastructure:
Prefect calls `graph.invoke()` as a task, FastAPI exposes a streaming
endpoint, Docker gets the new packages, and the old skeleton agent files
are cleanly retired.

---

## 5.1 — File Structure After Migration

```
python-service/app/modules/
├── llm/
│   ├── audit.py                    ← keep (legacy enrichment_flow still uses it)
│   ├── backends.py                 ← RETIRE after all callers migrate to model_factory
│   ├── model_registry.py           ← RETIRE (replaced by model_factory)
│   ├── model_factory.py            ← NEW (Phase 1) — build_chat_model()
│   ├── cost_tracker.py             ← UPDATE (add DeepSeek, Gemini, Ollama pricing)
│   ├── budget_guard.py             ← keep unchanged
│   └── langsmith_callback.py       ← NEW (Phase 4) — QDBCostCallback
│
├── agents/
│   ├── graph/
│   │   ├── __init__.py
│   │   ├── state.py                ← NEW (Phase 2) — GraphState TypedDict
│   │   ├── analysis_graph.py       ← NEW (Phase 2) — build_analysis_graph()
│   │   ├── models.py               ← NEW (Phase 3) — ResearchContext, TradeParams, DailyBrief
│   │   ├── prompts.py              ← NEW (Phase 3) — prompt builders
│   │   └── nodes/
│   │       ├── budget_check.py     ← NEW (Phase 3)
│   │       ├── data_node.py        ← NEW (Phase 3) — wraps DataAgent
│   │       ├── ml_node.py          ← NEW (Phase 3) — wraps MLAgent
│   │       ├── research_node.py    ← NEW (Phase 3)
│   │       ├── strategy_node.py    ← NEW (Phase 3)
│   │       ├── synthesis_node.py   ← NEW (Phase 3)
│   │       ├── persist_node.py     ← NEW (Phase 3)
│   │       └── end_early.py        ← NEW (Phase 3)
│   │
│   ├── base_agent.py               ← keep (DataAgent + MLAgent still use it)
│   ├── data_agent.py               ← keep (called by data_node)
│   ├── ml_agent.py                 ← keep (called by ml_node)
│   ├── research_agent.py           ← RETIRE after research_node implemented
│   ├── strategy_agent.py           ← RETIRE after strategy_node implemented
│   ├── synthesis_agent.py          ← RETIRE after synthesis_node implemented
│   │
│   ├── flows/
│   │   ├── multi_agent_analysis_flow.py  ← UPDATE (call graph.invoke instead of agent classes)
│   │   └── __init__.py
│   │
│   ├── api/
│   │   └── agent_api.py            ← UPDATE (add streaming endpoint)
│   └── db/
│       └── schema.py               ← keep (create_agent_tables still needed at startup)
```

---

## 5.2 — Docker Changes

### `python-service/requirements.txt` additions (from Phase 1)

```
langgraph>=0.2
langchain-core>=0.3
langchain-anthropic>=0.3
langchain-openai>=0.2
langchain-google-genai>=2.0
langchain-ollama>=0.2
langsmith>=0.2
```

### `docker-compose.yml` environment additions

```yaml
services:
  python-service:
    environment:
      # LangSmith
      - LANGCHAIN_TRACING_V2=true
      - LANGCHAIN_API_KEY=${LANGCHAIN_API_KEY}
      - LANGCHAIN_PROJECT=marketai-options-analysis

      # DeepSeek
      - DEEPSEEK_API_KEY=${DEEPSEEK_API_KEY}
      - DEEPSEEK_BASE_URL=https://api.deepseek.com/v1

      # Agent model aliases (override per deploy)
      - COORDINATOR_MODEL=haiku
      - RESEARCH_MODEL=sonnet
      - STRATEGY_MODEL=sonnet
      - SYNTHESIS_MODEL=sonnet
```

No new containers are needed — LangGraph runs inside the existing
`python-service` container alongside FastAPI and Prefect.

---

## 5.3 — Prefect Flow Update

**File**: `agents/flows/multi_agent_analysis_flow.py`

Replace the old agent class invocations with a single `graph.invoke()` task:

```python
from prefect import flow, task, get_run_logger
from langchain_core.runnables import RunnableConfig
from app.modules.agents.graph.analysis_graph import build_analysis_graph
from app.modules.llm.langsmith_callback import QDBCostCallback

_graph = None  # module-level singleton, built once per worker

def _get_graph():
    global _graph
    if _graph is None:
        _graph = build_analysis_graph()
    return _graph


@task(name="run_analysis_graph", retries=1, retry_delay_seconds=60)
def run_analysis_graph_task(
    symbols: list[str],
    target_date: str,
    model_aliases: dict,
    dry_run: bool = False,
) -> dict:
    logger = get_run_logger()
    config = RunnableConfig(
        callbacks=[QDBCostCallback("prefect_analysis_flow")],
        tags=["production", f"date:{target_date}"],
        metadata={"target_date": target_date, "symbols": symbols},
        run_name=f"options-analysis-{target_date}",
    )

    initial_state = {
        "target_date":   target_date,
        "symbols":       symbols,
        "model_aliases": model_aliases,
        "dry_run":       dry_run,
        # all other fields initialised empty by LangGraph
        "signal_batches": [],
        "scored_batches": [],
        "flagged_signals": [],
        "trade_params":    [],
        "errors":          [],
        "budget_ok":       True,
        "total_signals":   0,
        "total_flagged":   0,
        "research_context": None,
        "daily_brief":     None,
    }

    result = _get_graph().invoke(initial_state, config=config)
    logger.info(
        "Graph complete: %d flagged → %d trade params | brief=%s",
        result.get("total_flagged", 0),
        len(result.get("trade_params", [])),
        bool(result.get("daily_brief")),
    )
    return result


@flow(
    name="multi_agent_options_analysis",
    description="LangGraph analysis pipeline orchestrated by Prefect",
    log_prints=True,
)
def multi_agent_analysis_flow(
    symbols: list[str] | None = None,
    target_date: str | None = None,
    model_aliases: dict | None = None,
    dry_run: bool = False,
) -> dict:
    from datetime import date, timedelta
    d      = target_date or str(date.today() - timedelta(days=1))
    syms   = symbols or WATCHLIST
    models = model_aliases or {}

    return run_analysis_graph_task(syms, d, models, dry_run)
```

---

## 5.4 — FastAPI Streaming Endpoint

LangGraph supports `astream()` — stream state updates to the client as
each node completes. This lets the Angular dashboard show live progress.

**Update** `agents/api/agent_api.py`:

```python
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from langchain_core.runnables import RunnableConfig
from app.modules.agents.graph.analysis_graph import build_analysis_graph
import json

router = APIRouter(prefix="/agents", tags=["agents"])
_graph = build_analysis_graph()


@router.post("/analyze/stream")
async def stream_analysis(body: AnalyzeRequest):
    """
    SSE endpoint — streams state updates as each node completes.
    Angular subscribes with EventSource and updates the dashboard live.
    """
    initial_state = _build_initial_state(body)
    config = RunnableConfig(
        tags=["stream", f"date:{body.target_date or 'yesterday'}"],
    )

    async def event_generator():
        async for node_name, state_update in _graph.astream(
            initial_state, config=config, stream_mode="updates"
        ):
            payload = {
                "node":   node_name,
                "update": {k: v for k, v in state_update.items()
                           if k not in ("feature_matrix",)},  # exclude large blobs
            }
            yield f"data: {json.dumps(payload)}\n\n"
        yield "data: {\"done\": true}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.post("/analyze")
async def trigger_analysis(body: AnalyzeRequest):
    """Non-streaming invoke — returns when graph completes."""
    initial_state = _build_initial_state(body)
    result = await _graph.ainvoke(initial_state)
    return {
        "flagged":      result.get("total_flagged", 0),
        "trade_params": len(result.get("trade_params", [])),
        "brief":        result.get("daily_brief"),
    }
```

---

## 5.5 — Human-in-the-Loop (Optional / Phase 5B)

If the user wants a human approval step before strategy parameters are
generated (e.g. review flagged signals after `ml_node`):

```python
# Compile with interrupt
from langgraph.checkpoint.postgres import PostgresSaver

checkpointer = PostgresSaver(conn=get_pg_connection())
graph = build_analysis_graph().compile(
    checkpointer=checkpointer,
    interrupt_after=["ml_node"],
)

# First invoke — runs to ml_node, then pauses
thread_id = "run-2026-06-07-001"
graph.invoke(initial_state, config={"configurable": {"thread_id": thread_id}})

# Human reviews state["flagged_signals"] via Angular UI or API
# POST /api/v1/agents/approve/{thread_id}  → resumes graph from ml_node

# Resume — runs research → strategy → synthesis
graph.invoke(None, config={"configurable": {"thread_id": thread_id}})
```

New endpoints needed:
```
GET  /api/v1/agents/runs/{thread_id}/state     → current paused state
POST /api/v1/agents/runs/{thread_id}/resume    → resume from interrupt
POST /api/v1/agents/runs/{thread_id}/signals/{id}/remove  → remove a signal before resuming
```

---

## 5.6 — Migration Safety Rules

1. **No flag day** — old `enrichment_flow.py` keeps running unchanged. LangGraph
   flow runs on a separate Prefect schedule (22:45 ET vs 22:30 ET for enrichment).
2. **Retire files one-by-one** — only delete `research_agent.py`, `strategy_agent.py`,
   `synthesis_agent.py` after their graph node equivalents pass integration tests.
3. **Keep `llm/audit.py`** until `enrichment_flow.py` is migrated to LangGraph
   (separate effort, not in this phase).
4. **Feature parity check** — before retiring each agent file, confirm:
   - LangSmith shows the equivalent trace
   - `llm_audit_log` row is written via `QDBCostCallback`
   - `agent_trade_params` / `daily_briefs` write succeeds

---

## 5.7 — Rollout Sequence

| Step | Action | Validation |
|---|---|---|
| 1 | Add packages to `requirements.txt`, rebuild Docker | Import `langgraph` without error |
| 2 | Set env vars in `.env` and `docker-compose.yml` | `build_chat_model("sonnet")` returns object |
| 3 | `LANGCHAIN_TRACING_V2=true` in dev | Test trace appears in LangSmith UI |
| 4 | Deploy `analysis_graph.py` with stub nodes | Smoke test: `dry_run=True`, full graph path traced |
| 5 | Implement code nodes (budget, data, ml) | Integration test with real QuestDB data |
| 6 | Implement LLM nodes (research, strategy, synthesis) | End-to-end test on one symbol |
| 7 | Wire Prefect schedule (22:45 ET) | First nightly run — check LangSmith + QuestDB |
| 8 | Enable streaming endpoint | Angular EventSource test |
| 9 | Retire old agent files | All tests green |

---

## Phase 5 Deliverables

- [ ] `requirements.txt` — langgraph + provider packages added
- [ ] `docker-compose.yml` — env vars for LangSmith + DeepSeek + agent models
- [ ] `agents/flows/multi_agent_analysis_flow.py` — updated to call `graph.invoke()`
- [ ] `agents/api/agent_api.py` — streaming SSE endpoint added
- [ ] Prefect schedule registered (22:45 ET)
- [ ] `PostgresSaver` checkpointer configured (Phase 5B — human-in-the-loop)
- [ ] Old skeleton agent files retired (post integration tests)

## Commit checkpoint

```
feat(agents/phase5): Docker + Prefect + streaming endpoint + migration guide
```

---

## Full Phase Timeline

| Phase | Estimated effort | Blocker |
|---|---|---|
| 1 — Foundation (deps, model factory, LangSmith) | 1–2 days | LangSmith API key |
| 2 — Graph design (state + topology) | 1 day | Phase 1 complete |
| 3 — Agent nodes (implementation) | 3–5 days | Agent role definitions finalised |
| 4 — Observability (callback, pricing, alerts) | 1 day | Phase 3 complete |
| 5 — Deployment (Docker, Prefect, streaming) | 1–2 days | Phases 1–4 complete |
| **Total** | **7–11 days** | |

Phase 3 is the critical path — agent role definitions must be finalised before
node implementation begins. The user noted adjustments to agent definitions are pending.
