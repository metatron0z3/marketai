# MarketAI — Agentic Architecture Overview

**Decision**: LangGraph  
**Branch**: `multi_agentic_analysis`  
**Status**: Planning — skeleton in place, migration in progress

---

## Why LangGraph

| Criterion | LangGraph | PydanticAI | CrewAI |
|---|---|---|---|
| Observability (LangSmith) | ✅ Native, first-class | ❌ None | ⚠️ LangSmith via adapter |
| Conditional / looping graphs | ✅ Core feature | ⚠️ Manual | ⚠️ Limited |
| Human-in-the-loop | ✅ Checkpointing built in | ❌ Manual | ⚠️ Limited |
| Model-agnostic | ✅ `BaseChatModel` interface | ✅ Yes | ✅ Yes |
| FastAPI integration | ✅ Stream-compatible | ✅ Native | ⚠️ Workarounds |
| Maturity / ecosystem | ✅ Large, battle-tested | ⚠️ ~1 year old | ✅ Good |
| Structured output | ✅ `.with_structured_output()` | ✅ Native | ✅ Yes |

The deciding factor is **LangSmith observability** — every node execution, token count, latency,
prompt, and response is traced automatically without any custom audit log code. This replaces
the hand-rolled `agent_run_log` and `llm_audit_log` tables with a richer, searchable UI.

---

## What Changes vs the Current Skeleton

The skeleton built in this branch (`app/modules/agents/`) is a good foundation.
LangGraph replaces the *execution mechanism* — not the business logic.

| Skeleton piece | LangGraph replacement |
|---|---|
| `BaseAgent` + `_llm()` | LangGraph node functions + `BaseChatModel` |
| `backends.py` (custom Protocol) | LangChain provider packages (`langchain_anthropic`, `langchain_openai`, etc.) |
| `model_registry.py` | `build_chat_model(alias)` → returns `BaseChatModel` |
| `multi_agent_analysis_flow.py` (Prefect tasks calling agents) | `StateGraph` with typed state + conditional edges |
| `_write_agent_run_log()` (manual QDB write) | LangSmith auto-tracing (zero code) |

Prefect **remains** as the outer scheduler and retry layer. LangGraph becomes the inner
execution engine. Prefect task → calls `graph.invoke(state)` → LangSmith traces it.

---

## Model Provider Map (model-agnostic)

All models accessed through `langchain`'s `BaseChatModel` interface.

| Alias | Provider | LangChain package | Notes |
|---|---|---|---|
| `haiku` | Anthropic | `langchain_anthropic` | `claude-haiku-4-5-20251001` — cheapest, fast |
| `sonnet` | Anthropic | `langchain_anthropic` | `claude-sonnet-4-6` — default mid-tier |
| `opus` | Anthropic | `langchain_anthropic` | `claude-opus-4-8` — highest capability |
| `gpt-4o-mini` | OpenAI | `langchain_openai` | Cost-competitive with Haiku |
| `gpt-4o` | OpenAI | `langchain_openai` | Strong reasoning |
| `o1` | OpenAI | `langchain_openai` | Reasoning model, high cost |
| `gemini-flash` | Google | `langchain_google_genai` | `gemini-2.0-flash` — fast |
| `gemini-pro` | Google | `langchain_google_genai` | `gemini-2.5-pro` — strong |
| `deepseek-chat` | DeepSeek | `langchain_openai` (OpenAI-compat.) | `deepseek-chat` — cheap, strong at code/reasoning |
| `deepseek-r1` | DeepSeek | `langchain_openai` (OpenAI-compat.) | `deepseek-reasoner` — chain-of-thought reasoning |
| `llama3` | Ollama | `langchain_ollama` | Local, zero cost, offline |

DeepSeek uses the OpenAI-compatible endpoint (`https://api.deepseek.com/v1`) — no separate SDK needed.

---

## Document Index

| Doc | Phase | Status |
|---|---|---|
| `00-overview.md` | — | ✅ This document |
| `01-foundation.md` | Phase 1 — Dependencies + LangSmith | 📋 Plan |
| `02-graph-design.md` | Phase 2 — State + graph topology | 📋 Plan |
| `03-agent-nodes.md` | Phase 3 — Each node in detail | 📋 Plan |
| `04-observability.md` | Phase 4 — LangSmith + cost callbacks | 📋 Plan |
| `05-deployment.md` | Phase 5 — Docker + Prefect wiring | 📋 Plan |

---

## High-Level Sequence

```
Phase 1: Install deps, wire LangSmith, build model factory
Phase 2: Define GraphState TypedDict, build StateGraph skeleton
Phase 3: Migrate each agent to a LangGraph node
Phase 4: LangSmith tracing + cost callback + alert thresholds
Phase 5: FastAPI streaming endpoint + Prefect task handoff + Docker
```

Each phase has its own document with implementation tasks,
file-level changes, and a commit checkpoint.

---

## Architecture Diagram

```
┌──────────────────────────────────────────────────────────────┐
│  Prefect Flow (schedules, retries)                           │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  LangGraph StateGraph                                  │  │
│  │                                                        │  │
│  │  START                                                 │  │
│  │    │                                                   │  │
│  │    ▼                                                   │  │
│  │  [budget_check] ──── EXCEEDED ──▶ END                 │  │
│  │    │                                                   │  │
│  │    ▼                                                   │  │
│  │  [data_node]   (code only — QuestDB + features)       │  │
│  │    │                                                   │  │
│  │    ▼                                                   │  │
│  │  [ml_node]     (code only — ConvictionScorer + SHAP)  │  │
│  │    │                                                   │  │
│  │    ├── NO FLAGS ──▶ [synthesis_node] ──▶ END          │  │
│  │    │                                                   │  │
│  │    ▼                                                   │  │
│  │  [research_node]  (1 LLM call — mid-tier)             │  │
│  │    │                                                   │  │
│  │    ▼                                                   │  │
│  │  [strategy_node]  (N LLM calls — 1 per flagged signal │  │
│  │    │               Send graph for parallel fan-out)    │  │
│  │    ▼                                                   │  │
│  │  [synthesis_node] (1 LLM call — full-tier)            │  │
│  │    │                                                   │  │
│  │    ▼                                                   │  │
│  │   END                                                  │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  Every node auto-traced to LangSmith ──▶ langsmith.com      │
└──────────────────────────────────────────────────────────────┘
```

---

## Key Design Rules (carry forward from skeleton)

1. **Causal integrity** — no node may read data timestamped after `state.target_date`
2. **Idempotency** — every node checks for existing results before making LLM calls
3. **Budget gate first** — `budget_check` node is always the first edge from START
4. **Structured output** — all LLM nodes use `.with_structured_output(PydanticModel)`, no JSON regex
5. **Prefect owns scheduling** — LangGraph owns execution — they do not overlap
