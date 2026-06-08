# Multi-Agent Options Analysis — Design Plan

**Branch**: `multi_agentic_analysis`  
**Framework**: LangGraph + LangSmith  
**Goal**: Replace the single-threaded LLM enrichment loop with a LangGraph `StateGraph`
pipeline — model-agnostic (Anthropic, OpenAI, Gemini, DeepSeek, Ollama), fully observable
via LangSmith, orchestrated by Prefect.

> **Detailed phase docs live in `docs/agentic/`** — this file is the top-level summary.
> See `docs/agentic/WORKLOG.md` for a per-commit description of work done.

---

## Framework Decision: LangGraph

Chosen over PydanticAI and CrewAI. Deciding factor: **LangSmith observability** —
every node execution, token count, latency, prompt, and graph path traced automatically,
zero custom audit code required for LangGraph nodes. Also provides:
- Conditional + looping graph edges (budget gate, ML gate, fan-out)
- Human-in-the-loop via `PostgresSaver` checkpointing (pause after `ml_node`, resume)
- FastAPI streaming via `graph.astream()` — Angular dashboard shows live node progress
- `.with_structured_output(PydanticModel)` — replaces all `_parse_json()` regex fallbacks

**Prefect remains** as the outer scheduler and retry layer.
LangGraph is the inner execution engine. Prefect task → `graph.invoke(state)` → LangSmith traces it.

---

## Model Providers (all via `langchain_*` packages)

| Alias | Provider | Package | Notes |
|---|---|---|---|
| `haiku` | Anthropic | `langchain-anthropic` | Fast, cheapest |
| `sonnet` | Anthropic | `langchain-anthropic` | Default mid-tier |
| `opus` | Anthropic | `langchain-anthropic` | Highest capability |
| `gpt-4o-mini` | OpenAI | `langchain-openai` | Cost-competitive with Haiku |
| `gpt-4o` | OpenAI | `langchain-openai` | Strong reasoning |
| `gemini-flash` | Google | `langchain-google-genai` | Fast, cheap |
| `gemini-pro` | Google | `langchain-google-genai` | Strong |
| `deepseek-chat` | DeepSeek | `langchain-openai` (compat.) | ~80% cheaper than Sonnet, strong |
| `deepseek-r1` | DeepSeek | `langchain-openai` (compat.) | Chain-of-thought, for complex sizing |
| `llama3` | Ollama | `langchain-ollama` | Local, zero cost |

DeepSeek uses `ChatOpenAI(base_url="https://api.deepseek.com/v1")` — no separate package.
All models accessed through a single `build_chat_model(alias) → BaseChatModel` factory.

---

## Architecture (LangGraph StateGraph)

```
Prefect flow  ──────►  graph.invoke(state)
                              │
                    ┌─────────▼──────────┐
                    │   budget_check     │ ← first edge from START
                    └─────────┬──────────┘
                    budget_ok │  budget_exceeded → end_early
                              ▼
                    ┌─────────────────────┐
                    │     data_node       │  code only — QuestDB → 60+ features
                    └─────────┬───────────┘
                              ▼
                    ┌─────────────────────┐
                    │      ml_node        │  code only — ConvictionScorer + SHAP
                    └─────────┬───────────┘
              no flags │      │ signals flagged
                       ▼      ▼
                    ┌─────────────────────┐
                    │   research_node     │  1 LLM call — contagion/Granger/squeeze
                    └─────────┬───────────┘
                              │  Send(signal) fan-out (one per flagged signal)
                    ┌─────────▼───────────┐
                    │   strategy_node ×N  │  1 LLM call per signal (parallel)
                    └─────────┬───────────┘
                              │  operator.add accumulates trade_params[]
                    ┌─────────▼───────────┐
                    │  synthesis_node     │  1 LLM call — daily brief
                    └─────────┬───────────┘
                    ┌─────────▼───────────┐
                    │    persist_node     │  code only — writes to QuestDB
                    └─────────────────────┘
```

**Shared state**: `GraphState` TypedDict flows through every node.
`trade_params` uses `Annotated[list, operator.add]` so parallel `Send` executions accumulate.

---

## Baseline — What Exists Today

| Component | File | Status |
|---|---|---|
| Feature builder (60+ features, 4 groups) | `tos/ml/features/tos_feature_builder.py` | ✅ Complete |
| ConvictionScorer (quality × direction × magnitude × regime) | `tos/ml/inference/conviction_scorer.py` | ✅ Complete |
| LLM enrichment (per-symbol, sequential, Anthropic-only) | `options/services/llm_enrichment.py` | 🔴 Sequential, one provider |
| LLMClient (Anthropic wrapper + audit log) | `llm/audit.py` | 🔴 Anthropic-hardwired |
| Research modules | `tos/ml/research/` (5 modules) | ✅ Complete, not wired to agents |
| Enrichment Prefect flow | `options/flows/enrichment_flow.py` | ⚠️ One agent role, sequential |

**Key gaps**:
- `LLMClient` imports `anthropic.Anthropic` directly — cannot switch providers
- Enrichment loop is sequential: one symbol → one prompt → one role
- Research modules (contagion, Granger, gamma squeeze, HDBSCAN) run independently
- No cross-symbol synthesis or trade strategy output

---

## Node Roles

### Analysis Graph (nightly, 22:45 ET)

| Node | Type | LLM calls/day | Structured output |
|---|---|---|---|
| `budget_check` | Code only | 0 | — |
| `data_node` | Code only | 0 | `SignalBatch` |
| `ml_node` | Code only | 0 | `ScoredBatch` (ConvictionScorer + SHAP) |
| `research_node` | LLM — mid-tier | 1 | `ResearchContext` |
| `strategy_node` | LLM — mid-tier × N | 5–15 | `TradeParams` per signal |
| `synthesis_node` | LLM — full-tier | 1 | `DailyBrief` |
| `persist_node` | Code only | 0 | — |
| `end_early` | Code only | 0 | — |

### Archive Graph (separate flow, weekly or milestone-triggered)

| Node | Type | LLM calls/run | Structured output |
|---|---|---|---|
| `archive_node` | LLM — full-tier | 3–5 | `ArchiveReport` |

The archive graph runs independently — separate Prefect flow, separate LangGraph `StateGraph`,
separate schedule. It does not share state with the analysis graph.

All LLM nodes use `.with_structured_output(PydanticModel)` — no JSON parsing or regex fallbacks.

---

## Archive Agent — Role and Scope

The `archive_node` is a standalone historical/education agent with a fundamentally different
job from the trading pipeline: it documents the project itself, not the market.

**Responsibilities**:

1. **Historical performance archive** — once real options data is flowing, reads QuestDB
   (`agent_trade_params`, `signal_catalog`, `conviction_scores`) to build a structured
   performance record: which signals were flagged, what the model recommended, what happened.
   This becomes the ground truth for backtesting and future model training.

2. **Development log** — reads git log, commit messages, and the `WORKLOG.md` to produce
   a human-readable, milestone-oriented account of how the project evolved. Surfaced as
   a `/project/history` section in the Angular frontend.

3. **Technical documentation** — generates detailed explanations of deeply technical subsystems
   (ConvictionScorer formula, walk-forward CV design, LangGraph graph topology, SHAP
   interpretation). Targeted at an informed reader who wants to understand not just what
   the system does, but why each design choice was made.

4. **Glossary maintenance** — owns `docs/glossary.html`. On each run, checks for new terms
   introduced since the last glossary update (new model names, new QDB tables, new agent
   nodes) and produces updated glossary entries with concrete examples.

5. **Frontend section** — coordinates with the Angular frontend to maintain a separate
   `/docs` section of the web UI: project history timeline, technical explainers, glossary,
   live performance archive. The NestJS backend exposes a new `GET /api/v1/archive/`
   router group that the Angular `ArchiveModule` consumes.

**Cadence**: weekly (Sunday 00:00 ET) + triggered on milestone commits (new agent shipped,
first real-data run, model retrain cycle complete).

**Model**: Sonnet or Opus — quality matters more than cost here. ~3–5 LLM calls per run.

**What it does NOT do**: it never touches `agent_trade_params` directly for strategy decisions,
never calls the analysis graph, never modifies signal scoring logic.

---

## Key State Fields

```python
class GraphState(TypedDict):
    target_date:      str
    symbols:          list[str]
    model_aliases:    dict[str, str]        # {"research": "sonnet", "strategy": "deepseek-chat"}
    dry_run:          bool

    # Budget
    budget_ok:            bool
    budget_daily_cap:     float
    budget_daily_spent:   float
    budget_monthly_cap:   float
    budget_monthly_spent: float

    # Data and ML
    signal_batches:   list[dict]
    scored_batches:   list[dict]
    flagged_signals:  list[dict]
    total_signals:    int
    total_flagged:    int

    # LLM outputs
    research_context: dict | None
    trade_params:     Annotated[list[dict], operator.add]   # fan-out accumulator
    daily_brief:      dict | None

    errors: list[str]
```

---

## Implementation Phases

| Phase | What | Key deliverable | Est. effort |
|---|---|---|---|
| **1 — Foundation** | LangGraph + langchain-* packages, `model_factory.py`, LangSmith project | `build_chat_model(alias)` returns any provider | 1–2 days |
| **2 — Graph skeleton** | `state.py` + `analysis_graph.py` with stub nodes | Full graph path runnable with `dry_run=True` | 1 day |
| **3 — Node impl.** | 8 node files, Pydantic models, prompt builders | End-to-end run on one symbol | 3–5 days |
| **4 — Observability** | `QDBCostCallback`, DeepSeek/Gemini pricing, LangSmith alerts | Cost written to `llm_audit_log` per node | 1 day |
| **5 — Deployment** | Docker env vars, Prefect `graph.invoke()`, FastAPI SSE | Angular dashboard shows live node progress | 1–2 days |

> **Phase 3 is the critical path** — agent role definitions must be finalised before node implementation begins.
> Detailed specs: [`docs/agentic/01-foundation.md`](agentic/01-foundation.md) → [`05-deployment.md`](agentic/05-deployment.md)

---

## Cost Estimate (Sonnet defaults)

| Node | Model | Calls/day | ~Tokens/call | Est. cost/day |
|---|---|---|---|---|
| `research_node` | Sonnet | 1 | 2,000 in + 500 out | ~$0.020 |
| `strategy_node` | Sonnet | 10 signals avg | 1,500 in + 400 out | ~$0.22 |
| `synthesis_node` | Sonnet | 1 | 3,000 in + 600 out | ~$0.025 |
| **Total** | | | | **~$0.27/day** |

**DeepSeek-chat alternative** (`RESEARCH_MODEL=deepseek-chat STRATEGY_MODEL=deepseek-chat`):
same quality, ~80% cheaper → **~$0.05/day**.

Fits within the existing $2.27/day daily budget cap.

---

## Environment Variables

```bash
# LangSmith (auto-traces all LangGraph invocations)
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=...
LANGCHAIN_PROJECT=marketai-options-analysis

# Provider keys (only the providers you use)
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
GEMINI_API_KEY=AIza...
DEEPSEEK_API_KEY=...
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
OLLAMA_HOST=http://localhost:11434

# Per-node model aliases (switch providers with zero code changes)
RESEARCH_MODEL=sonnet          # or: deepseek-chat, gpt-4o, gemini-pro, llama3
STRATEGY_MODEL=sonnet          # deepseek-r1 for complex sizing
SYNTHESIS_MODEL=sonnet
```

---

## Open Decisions (resolve before Phase 3 starts)

1. **Agent role definitions** — pending user adjustments before node implementation begins.
2. **Kelly sizing** — plan uses ½ Kelly with `MAX_POSITION_PCT` cap (production standard).
3. **Human approval gate** — optional: pause graph after `ml_node` via `PostgresSaver` checkpointing, resume after human review (`docs/agentic/05-deployment.md §5.5`).
4. **Signal threshold** — default: `conviction_score > 0.65 AND cluster_hit_rate > 0.55`. Adjust in `ml_node.py` constants.
5. **Ollama** — local GPU or cloud-only for initial version?
