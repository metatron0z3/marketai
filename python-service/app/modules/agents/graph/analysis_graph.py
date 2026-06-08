"""
build_analysis_graph() — assembles the LangGraph StateGraph for nightly options analysis.

Graph topology:
  START → budget_check
          ├── budget_exceeded → end_early → END
          └── ok → data_node → ml_node
                               ├── no_signals → synthesis_node → persist_node → END
                               └── has_signals → research_node → strategy_node×N
                                                                  → synthesis_node → persist_node → END

Prefect wraps graph.invoke(initial_state) as a single task.
LangSmith traces every node automatically when LANGCHAIN_TRACING_V2=true.
"""
from __future__ import annotations

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from app.modules.agents.graph.state import GraphState
from app.modules.agents.graph.nodes.budget_check  import budget_check_node
from app.modules.agents.graph.nodes.data_node     import data_node
from app.modules.agents.graph.nodes.ml_node       import ml_node
from app.modules.agents.graph.nodes.research_node import research_node
from app.modules.agents.graph.nodes.strategy_node import strategy_node
from app.modules.agents.graph.nodes.synthesis_node import synthesis_node
from app.modules.agents.graph.nodes.persist_node  import persist_node
from app.modules.agents.graph.nodes.end_early     import end_early_node


# ── Routing functions ─────────────────────────────────────────────────────────

def route_after_budget(state: GraphState) -> str:
    return "ok" if state.get("budget_ok", False) else "exceeded"


def route_after_ml(state: GraphState) -> str:
    return "has_signals" if (state.get("total_flagged") or 0) > 0 else "no_signals"


def route_to_strategy(state: GraphState) -> list[Send]:
    """Fan out: one Send per flagged signal → parallel strategy_node executions."""
    alias   = state.get("model_aliases", {}).get("strategy", "sonnet")
    dry_run = state.get("dry_run", False)
    return [
        Send("strategy_node", {
            "signal":           sig,
            "research_context": state.get("research_context"),
            "model_alias":      alias,
            "dry_run":          dry_run,
        })
        for sig in (state.get("flagged_signals") or [])
    ]


# ── Graph builder ─────────────────────────────────────────────────────────────

def build_analysis_graph(checkpointer=None):
    """
    Build and compile the analysis StateGraph.

    Args:
        checkpointer: optional LangGraph checkpointer (MemorySaver or PostgresSaver).
                      Required for human-in-the-loop or resume-on-failure.
    """
    graph = StateGraph(GraphState)

    # Register nodes
    graph.add_node("budget_check",   budget_check_node)
    graph.add_node("data_node",      data_node)
    graph.add_node("ml_node",        ml_node)
    graph.add_node("research_node",  research_node)
    graph.add_node("strategy_node",  strategy_node)
    graph.add_node("synthesis_node", synthesis_node)
    graph.add_node("persist_node",   persist_node)
    graph.add_node("end_early",      end_early_node)

    # Entry point
    graph.add_edge(START, "budget_check")

    # Budget gate
    graph.add_conditional_edges(
        "budget_check",
        route_after_budget,
        {"ok": "data_node", "exceeded": "end_early"},
    )

    # Data → ML (always linear)
    graph.add_edge("data_node", "ml_node")

    # ML gate: skip research+strategy if nothing flagged
    graph.add_conditional_edges(
        "ml_node",
        route_after_ml,
        {"has_signals": "research_node", "no_signals": "synthesis_node"},
    )

    # Research → strategy fan-out
    graph.add_conditional_edges("research_node", route_to_strategy, ["strategy_node"])

    # Strategy fan-in → synthesis
    graph.add_edge("strategy_node", "synthesis_node")

    # Synthesis → persist → done
    graph.add_edge("synthesis_node", "persist_node")
    graph.add_edge("persist_node",   END)
    graph.add_edge("end_early",      END)

    compile_kwargs = {}
    if checkpointer is not None:
        compile_kwargs["checkpointer"] = checkpointer

    return graph.compile(**compile_kwargs)


# ── Default initial state ─────────────────────────────────────────────────────

def make_initial_state(
    target_date: str,
    symbols: list[str],
    model_aliases: dict[str, str] | None = None,
    dry_run: bool = False,
) -> dict:
    """Return a complete initial GraphState with all optional fields zeroed."""
    return {
        "target_date":          target_date,
        "symbols":              symbols,
        "model_aliases":        model_aliases or {},
        "dry_run":              dry_run,
        "budget_daily_cap":     0.0,
        "budget_daily_spent":   0.0,
        "budget_monthly_cap":   0.0,
        "budget_monthly_spent": 0.0,
        "budget_ok":            False,
        "signal_batches":       [],
        "total_signals":        0,
        "scored_batches":       [],
        "flagged_signals":      [],
        "total_flagged":        0,
        "research_context":     None,
        "trade_params":         [],
        "daily_brief":          None,
        "errors":               [],
    }
