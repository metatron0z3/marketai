# Phase 2 — Graph Design: State, Nodes, and Edges

## Goal

Define the `GraphState` TypedDict, map every agent to a LangGraph node,
and wire conditional edges so the graph routes correctly — skipping LLM-heavy
nodes when there's nothing actionable, and ending early when the budget is exceeded.

---

## 2.1 — GraphState

The state is the single shared object that flows through every node.
Each node reads from it and returns a partial dict that gets merged in.

**File**: `python-service/app/modules/agents/graph/state.py`

```python
from __future__ import annotations
from typing import Annotated, Any
from typing_extensions import TypedDict
from langgraph.graph.message import add_messages


class GraphState(TypedDict):
    # ── Inputs (set once by the caller) ────────────────────────────────
    target_date:   str
    symbols:       list[str]
    model_aliases: dict[str, str]        # {"research": "deepseek-chat", ...}
    dry_run:       bool

    # ── Budget (set by budget_check, decremented by LLM nodes) ─────────
    budget_daily_cap:       float
    budget_daily_spent:     float
    budget_monthly_cap:     float
    budget_monthly_spent:   float
    budget_ok:              bool          # False → graph routes to END

    # ── Data layer (DataNode output) ───────────────────────────────────
    signal_batches:    list[dict]         # one SignalBatch per symbol
    total_signals:     int

    # ── ML layer (MLNode output) ───────────────────────────────────────
    scored_batches:    list[dict]         # one ScoredBatch per symbol
    flagged_signals:   list[dict]         # signals above conviction threshold
    total_flagged:     int

    # ── Research layer (ResearchNode output) ───────────────────────────
    research_context:  dict | None

    # ── Strategy layer (StrategyNode output) ───────────────────────────
    trade_params:      list[dict]         # one TradeParams per flagged signal

    # ── Synthesis layer (SynthesisNode output) ─────────────────────────
    daily_brief:       dict | None

    # ── Errors / warnings accumulated across nodes ─────────────────────
    errors:            list[str]
```

### Design notes

- **No `Annotated[..., add_messages]`** — this is not a conversational agent.
  State is a pipeline accumulator, not a chat history.
- Nodes return `dict` slices — LangGraph merges them into state automatically.
  A node that only updates `research_context` returns `{"research_context": {...}}`.
- All fields have defaults or are `None` — LangGraph requires no field to be
  missing when the graph starts. The caller provides `target_date`, `symbols`,
  `model_aliases`, and `dry_run`; everything else starts empty.

---

## 2.2 — Node Map

| Node name | Type | State reads | State writes |
|---|---|---|---|
| `budget_check` | Code | — | `budget_*`, `budget_ok` |
| `data_node` | Code | `target_date`, `symbols` | `signal_batches`, `total_signals` |
| `ml_node` | Code | `signal_batches` | `scored_batches`, `flagged_signals`, `total_flagged` |
| `research_node` | LLM (mid) | `scored_batches`, `flagged_signals` | `research_context` |
| `strategy_node` | LLM (mid) × N | `flagged_signals`, `research_context` | `trade_params` |
| `synthesis_node` | LLM (full) | `trade_params`, `research_context` | `daily_brief` |
| `persist_node` | Code | all output fields | — (side effects) |
| `end_early` | Code | `errors` | — (logs and exits) |

---

## 2.3 — Graph Topology

**File**: `python-service/app/modules/agents/graph/analysis_graph.py`

```python
from langgraph.graph import StateGraph, END, START
from app.modules.agents.graph.state import GraphState

def build_analysis_graph() -> StateGraph:
    graph = StateGraph(GraphState)

    # ── Register nodes ──────────────────────────────────────────────
    graph.add_node("budget_check",  budget_check_node)
    graph.add_node("data_node",     data_node)
    graph.add_node("ml_node",       ml_node)
    graph.add_node("research_node", research_node)
    graph.add_node("strategy_node", strategy_node)
    graph.add_node("synthesis_node",synthesis_node)
    graph.add_node("persist_node",  persist_node)
    graph.add_node("end_early",     end_early_node)

    # ── Entry point ─────────────────────────────────────────────────
    graph.add_edge(START, "budget_check")

    # ── Conditional: budget exceeded? ───────────────────────────────
    graph.add_conditional_edges(
        "budget_check",
        route_after_budget,
        {"ok": "data_node", "exceeded": "end_early"},
    )

    # ── Linear: data → ml ───────────────────────────────────────────
    graph.add_edge("data_node", "ml_node")

    # ── Conditional: any flagged signals? ───────────────────────────
    graph.add_conditional_edges(
        "ml_node",
        route_after_ml,
        {"has_signals": "research_node", "no_signals": "synthesis_node"},
    )

    # ── Linear: research → strategy ─────────────────────────────────
    graph.add_edge("research_node", "strategy_node")

    # ── Linear: strategy → synthesis ────────────────────────────────
    graph.add_edge("strategy_node", "synthesis_node")

    # ── Linear: synthesis → persist ─────────────────────────────────
    graph.add_edge("synthesis_node", "persist_node")

    # ── Terminal edges ───────────────────────────────────────────────
    graph.add_edge("persist_node", END)
    graph.add_edge("end_early",    END)

    return graph.compile()
```

### Routing functions

```python
def route_after_budget(state: GraphState) -> str:
    return "ok" if state["budget_ok"] else "exceeded"

def route_after_ml(state: GraphState) -> str:
    return "has_signals" if state["total_flagged"] > 0 else "no_signals"
```

---

## 2.4 — Strategy Node: Fan-Out Pattern

`strategy_node` must run one LLM call per flagged signal. LangGraph handles
this with the **Send API** — spawning parallel subgraph executions.

```python
from langgraph.types import Send

def route_to_strategy(state: GraphState) -> list[Send]:
    """Fan out: one Send per flagged signal."""
    return [
        Send("strategy_node", {
            "signal":           sig,
            "research_context": state["research_context"],
            "model_alias":      state["model_aliases"].get("strategy", "sonnet"),
        })
        for sig in state["flagged_signals"]
    ]
```

Each `Send` spawns an independent strategy_node execution. Results are
collected back into `state["trade_params"]` as a list via a reducer.

This requires a small state adjustment — `trade_params` uses `Annotated` with
an `operator.add` reducer so parallel results accumulate:

```python
import operator
from typing import Annotated

class GraphState(TypedDict):
    ...
    trade_params: Annotated[list[dict], operator.add]   # accumulates across Send invocations
```

---

## 2.5 — Checkpointing (Human-in-the-Loop)

LangGraph's checkpointer saves graph state after each node. This enables:
- **Resuming** a failed run at the node where it broke
- **Human review** — pause after `ml_node`, let a human approve the flagged
  signals, then resume into `research_node`
- **Inspection** — replay any prior run's full state

```python
from langgraph.checkpoint.memory import MemorySaver  # dev/testing
# from langgraph.checkpoint.postgres import PostgresSaver  # production

checkpointer = MemorySaver()
graph = build_analysis_graph().compile(checkpointer=checkpointer)

# Pause after ml_node for human review:
graph = build_analysis_graph().compile(
    checkpointer=checkpointer,
    interrupt_after=["ml_node"],   # pauses here, waits for resume
)
```

For production, swap `MemorySaver` for `PostgresSaver` pointed at the
existing Postgres instance (TOS postgres or a dedicated DB).

---

## 2.6 — Graph Invocation

```python
# Synchronous (Prefect task)
state = graph.invoke({
    "target_date":   "2026-06-07",
    "symbols":       ["NVDA", "TSLA", "SPY"],
    "model_aliases": {"research": "deepseek-chat", "strategy": "sonnet"},
    "dry_run":       False,
    # all other fields initialised to empty by LangGraph
})

# Streaming (FastAPI SSE endpoint)
async for chunk in graph.astream(initial_state, stream_mode="updates"):
    yield f"data: {json.dumps(chunk)}\n\n"
```

---

## 2.7 — File Layout for Phase 2

```
python-service/app/modules/agents/
├── graph/
│   ├── __init__.py
│   ├── state.py               ← GraphState TypedDict
│   ├── analysis_graph.py      ← build_analysis_graph() + routing functions
│   └── nodes/
│       ├── __init__.py
│       ├── budget_check.py
│       ├── data_node.py
│       ├── ml_node.py
│       ├── research_node.py
│       ├── strategy_node.py
│       ├── synthesis_node.py
│       ├── persist_node.py
│       └── end_early.py
```

The existing `agents/data_agent.py`, `ml_agent.py`, etc. become the *business logic* 
imported by the node files. The nodes themselves are thin wrappers that read from
`GraphState` and return a state slice.

---

## Phase 2 Deliverables

- [ ] `agents/graph/state.py` — `GraphState` TypedDict with `operator.add` on `trade_params`
- [ ] `agents/graph/analysis_graph.py` — `build_analysis_graph()` with all nodes + edges
- [ ] Stub implementations for all 8 node files (enough to run the graph end-to-end)
- [ ] Routing functions: `route_after_budget`, `route_after_ml`, `route_to_strategy`
- [ ] Smoke test: invoke graph with `dry_run=True` — no LLM calls, full path traced

## Commit checkpoint

```
feat(agents/phase2): StateGraph skeleton — state, nodes, conditional edges, fan-out
```
