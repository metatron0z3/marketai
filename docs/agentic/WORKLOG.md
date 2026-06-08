# Agentic Architecture — Work Log

Running record of what was done, why, and what comes next.
Updated with every commit on `multi_agentic_analysis`.

---

## 2026-06-07 — Session 1: Plan + Skeleton

### Decision: LangGraph

Chose LangGraph over PydanticAI and CrewAI. Deciding factor was **LangSmith observability** —
every node execution, prompt, token count, and latency traced automatically with zero audit code.
PydanticAI has no observability layer; CrewAI requires adapters. DeepSeek added to the model
provider map using the OpenAI-compatible endpoint (no separate package needed).

---

### Commit: `docs(agentic): add overview — LangGraph decision, provider map, architecture diagram`
**File**: `00-overview.md`

Written first to lock the decision and establish the full provider map before writing
any implementation plan. Includes the StateGraph topology diagram with Prefect as the
outer scheduler and LangGraph as the inner execution engine.

Key decisions captured:
- Prefect owns scheduling + retries; LangGraph owns execution — they do not overlap
- DeepSeek-chat and DeepSeek-R1 added via `langchain_openai` + `DEEPSEEK_BASE_URL`
- LangSmith replaces the hand-rolled `agent_run_log` QDB table for LLM nodes
- All 5 design rules carried forward from the pre-LangGraph skeleton

---

### Commit: `docs(agentic/phase1): foundation — LangGraph deps, model factory, DeepSeek, LangSmith`
**File**: `01-foundation.md`

Specifies every dependency change needed (`langgraph`, `langchain-anthropic`,
`langchain-openai`, `langchain-google-genai`, `langchain-ollama`, `langsmith`),
all new env vars, and the `build_chat_model(alias)` factory that replaces the
custom `LLMBackend` protocol from `backends.py`.

Why factory over direct imports: every node resolves its model at call time from an
alias string, which means switching `RESEARCH_MODEL=deepseek-chat` in `.env` reroutes
all research_node calls without any code change. `@lru_cache` keeps one instance per alias.

DeepSeek note: `deepseek-chat` uses `ChatOpenAI` pointed at `https://api.deepseek.com/v1` —
no new package. `deepseek-reasoner` (R1) is the chain-of-thought model, used as an
on-demand override for complex position sizing in strategy_node.

---

### Commit: `docs(agentic/phase2): graph design — GraphState, node map, topology, Send fan-out`
**File**: `02-graph-design.md`

Defines the `GraphState` TypedDict — the single object that flows through every node.
Two key design choices:
1. `trade_params` uses `Annotated[list, operator.add]` reducer so parallel `Send`
   invocations from strategy_node all accumulate into one list rather than overwriting.
2. Two conditional edges: budget gate (immediately after START) and ML gate
   (skip research + strategy if no signals are flagged). Graph never wastes LLM calls.

Also documents the checkpointing setup for future human-in-the-loop: pause after `ml_node`,
let a human review flagged signals in the UI, resume into research_node.

---

### Commit: `docs(agentic/phase3): agent nodes — anatomy, pydantic models, prompts, per-node impls`
**File**: `03-agent-nodes.md`

Most detailed phase doc — covers all 8 nodes. Key change from the pre-LangGraph skeleton:
every LLM node uses `.with_structured_output(PydanticModel)` instead of returning raw text
that gets parsed with `_parse_json()` + regex fallback. This makes structured output
a framework guarantee, not a runtime hope.

Pydantic output models defined: `ResearchContext`, `TradeParams` (with `PositionSizing`),
`DailyBrief`. These will live in `agents/graph/models.py`.

Note: agent role definitions are pending user review before Phase 3 implementation begins.

---

### Commit: `docs(agentic/phase4): observability — LangSmith auto-tracing, QDB callback, cost table`
**File**: `04-observability.md`

LangSmith auto-traces everything — prompts, responses, tokens, latency, graph path —
with no code. The one gap: `budget_guard.py` reads from `llm_audit_log` (QuestDB) to
enforce daily/monthly caps. LangSmith doesn't write there.

Solution: `QDBCostCallback` — a `BaseCallbackHandler` that fires after every LLM call
and writes to `llm_audit_log`. Attached via `RunnableConfig(callbacks=[...])` on each
LLM node. Fire-and-forget (never breaks the LLM call if it fails).

Also adds DeepSeek, Gemini, and Ollama pricing rows to `cost_tracker.py` so `compute_cost()`
handles all providers. Recommended LangSmith alert rules documented.

---

### Commit: `docs(agentic/phase5): deployment — Docker, Prefect graph.invoke(), SSE streaming, migration`
**File**: `05-deployment.md`

How LangGraph slots into the existing infrastructure:
- `python-service` container gets new packages — no new container
- Prefect flow is simplified to one task: `graph.invoke(initial_state, config=config)`
- FastAPI gets a new `POST /agents/analyze/stream` SSE endpoint using `graph.astream()`
  so Angular can show live node-by-node progress
- Migration safety rule: no flag day — old `enrichment_flow.py` keeps running on its
  22:30 ET schedule; new LangGraph flow runs at 22:45 ET in parallel until stable

Full timeline: 7–11 days, Phase 3 on critical path (blocked on agent role definitions).

---

### Commit: `feat(agents): skeleton module structure — pre-LangGraph agent classes + API`
**Files**: `app/modules/agents/`, `app/modules/llm/backends.py`, `app/modules/llm/model_registry.py`

The initial agent skeleton built before switching to LangGraph. Retained because:
- `data_agent.py` and `ml_agent.py` are code-only — graph nodes will import them directly
- `base_agent.py` provides `AgentContext` still used during migration
- `backends.py` / `model_registry.py` will be retired once `model_factory.py` is in place
- QuestDB schema (`agents/db/schema.py`) and API router (`agents/api/agent_api.py`) are
  valid and don't need LangGraph to function

---

---

## 2026-06-07 — Session 2: Rewrite `docs/multi-agent-plan.md`

### Commit: `docs: rewrite multi-agent-plan to reflect LangGraph architecture`
**File**: `docs/multi-agent-plan.md`

The "core plan" file still described the pre-LangGraph design: custom `LLMBackend` Protocol,
`model_registry.py` with `get_backend()`, Prefect-only multi-agent flow calling agent class
methods directly. It had no mention of LangGraph, LangSmith, `GraphState`, `StateGraph`,
`build_chat_model()`, DeepSeek, `QDBCostCallback`, or SSE streaming.

Full rewrite to match the `docs/agentic/` phase documents:
- Framework decision section (LangGraph chosen over PydanticAI + CrewAI for LangSmith observability)
- Provider table with all 10 aliases including `deepseek-chat` and `deepseek-r1`
- `StateGraph` topology diagram replacing the old CoordinatorAgent tree
- `GraphState` TypedDict snippet showing `operator.add` reducer for fan-out
- Node Roles table (8 nodes, code vs LLM, structured output type)
- Implementation Phases table pointing to `docs/agentic/` for details
- Updated cost estimate (DeepSeek-chat alternative: ~$0.05/day vs $0.27/day)
- Environment variables section (LangSmith + DeepSeek + per-node aliases)
- Open Decisions replacing the old "Open Questions" (reflects LangGraph decisions already made)

Old custom backend code (Steps 1–7, 120+ lines) fully removed.

---

---

## 2026-06-07 — Session 2: Historical/Education Agent added

### Commit: `docs(agents): add archive_node — historical archive, glossary, education agent`
**Files**: `docs/multi-agent-plan.md`, `docs/agentic/03-agent-nodes.md`

User identified a missing agent: one whose job is to document the project itself, not the market.
The trading pipeline agents (data → ml → research → strategy → synthesis) all serve the daily
analysis workflow. The archive/historian agent runs on a completely separate cadence (weekly +
milestone-triggered) and has a different audience: developers and informed readers, not traders.

Key design decisions captured:
- **Separate graph**: `ArchiveGraphState` + `build_archive_graph()` — no shared state with the
  analysis graph. Different Prefect flow, different schedule, different `StateGraph`.
- **4 responsibilities**: historical performance archive, development log (from git + WORKLOG),
  technical explainers for deeply technical subsystems, glossary maintenance
- **Glossary ownership**: the archive agent owns `docs/glossary.html`. On each run it checks for
  new terms introduced since the last update and produces new entries with concrete examples.
- **Frontend section**: a separate `/docs` section in Angular (`ArchiveModule`) served by a new
  `GET /api/v1/archive/` NestJS router group — completely isolated from the trading dashboard.
- **3 QuestDB tables added**: `project_milestones`, `technical_explainers`, `archive_reports`
- **Model choice**: Sonnet by default, Opus override for the deep technical explainer pass.
  `ARCHIVE_MODEL` and `ARCHIVE_DEEP_MODEL` env var aliases follow the same pattern as other nodes.

Why not just a Prefect task? The archive job needs structured, typed output that can be reliably
deserialized — `ArchiveReport` → `GlossaryEntry[]` + `Milestone[]` + `TechnicalExplainer[]`.
LangGraph's `.with_structured_output()` gives that without regex fallbacks.

---

## What Comes Next (pending user agent adjustments)

1. User to finalize agent role definitions
2. Phase 1: install packages, create `model_factory.py`, set up LangSmith project
3. Phase 2: `state.py` + `analysis_graph.py` skeleton (can start immediately)
4. Phase 3: implement nodes one by one, commit per node
5. Phase 4: wire `QDBCostCallback`, add DeepSeek pricing
6. Phase 5: Docker + Prefect update + SSE endpoint
