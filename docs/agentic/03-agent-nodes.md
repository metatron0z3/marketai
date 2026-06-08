# Phase 3 — Agent Nodes: Detailed Implementation

## Goal

Implement each LangGraph node as a thin function that reads from `GraphState`,
delegates to the existing business logic (feature builder, ConvictionScorer, research modules),
and returns a state slice. LLM nodes use `.with_structured_output()` — no JSON parsing.

> **Note to reviewer**: the agent *roles* defined here are a starting point.
> Agent definitions will be adjusted before implementation begins.

---

## 3.1 — Node Anatomy

Every node follows this pattern:

```python
from app.modules.agents.graph.state import GraphState

def some_node(state: GraphState) -> dict:
    # 1. Read what you need from state
    # 2. Do the work (call existing services, or call the LLM)
    # 3. Return ONLY the fields you are updating
    return {"field_you_updated": result}
```

LLM nodes also specify the model alias from state:

```python
from app.modules.llm.model_factory import get_agent_model

def research_node(state: GraphState) -> dict:
    alias = state["model_aliases"].get("research", "sonnet")
    llm   = get_agent_model("research", override=alias)
    structured_llm = llm.with_structured_output(ResearchContext)
    ...
```

---

## 3.2 — budget_check_node

**File**: `agents/graph/nodes/budget_check.py`  
**Type**: Code only

```python
def budget_check_node(state: GraphState) -> dict:
    from app.modules.llm.budget_guard import check_budget, BudgetExceededError
    try:
        status = check_budget()
        return {
            "budget_daily_cap":     status["daily_cap"],
            "budget_daily_spent":   status["daily_spend"],
            "budget_monthly_cap":   status["monthly_cap"],
            "budget_monthly_spent": status["monthly_spend"],
            "budget_ok":            True,
        }
    except BudgetExceededError as exc:
        return {
            "budget_ok": False,
            "errors":    [f"Budget exceeded: {exc}"],
        }
```

**Routing**: If `budget_ok=False`, the graph routes to `end_early` — no LLM calls made.

---

## 3.3 — data_node

**File**: `agents/graph/nodes/data_node.py`  
**Type**: Code only — wraps `DataAgent`

```python
def data_node(state: GraphState) -> dict:
    from app.modules.agents.data_agent import DataAgent
    from app.modules.agents.base_agent import AgentContext

    ctx = AgentContext(
        run_id=state.get("run_id", ""),
        target_date=state["target_date"],
        symbols=state["symbols"],
        budget_remaining_usd=state["budget_daily_cap"] - state["budget_daily_spent"],
    )

    agent = DataAgent()
    batches, total = [], 0
    errors = []

    for symbol in state["symbols"]:
        result = agent.run(ctx, symbol=symbol)
        if result.get("batch"):
            batches.append(result["batch"].__dict__)
            total += result["count"]
        elif result["count"] == 0:
            pass   # no signals for this symbol today — normal
        else:
            errors.append(f"DataAgent {symbol}: {result.get('error')}")

    return {
        "signal_batches": batches,
        "total_signals":  total,
        "errors":         errors,
    }
```

**What it does**: queries `signal_catalog` + QuestDB feature tables, builds
the 60+ feature matrix per symbol, ranks by `volume_ratio_20d × log_premium × iv_rank`,
groups into DTE/OTM fingerprint clusters.

---

## 3.4 — ml_node

**File**: `agents/graph/nodes/ml_node.py`  
**Type**: Code only — wraps `MLAgent` + `ConvictionScorer`

```python
def ml_node(state: GraphState) -> dict:
    from app.modules.agents.ml_agent import MLAgent
    from app.modules.agents.base_agent import AgentContext

    ctx = AgentContext(...)
    agent = MLAgent()
    scored_batches, flagged, errors = [], [], []

    for batch_dict in state["signal_batches"]:
        batch = _dict_to_signal_batch(batch_dict)
        result = agent.run(ctx, batch=batch)
        if result.get("scored_batch"):
            scored_batches.append(result["scored_batch"].__dict__)
            flagged.extend(_scored_to_dicts(result["scored_batch"].flagged))

    return {
        "scored_batches":  scored_batches,
        "flagged_signals": flagged,
        "total_flagged":   len(flagged),
        "errors":          errors,
    }
```

**What it does**: runs `ConvictionScorer` (quality × direction × magnitude × regime)
on every signal, computes SHAP top-3 features for flagged signals, looks up the
30-day cluster hit rate.

**Routing gate**: if `total_flagged == 0`, graph skips research + strategy and
goes straight to synthesis (which writes an "all quiet" brief).

---

## 3.5 — research_node

**File**: `agents/graph/nodes/research_node.py`  
**Type**: LLM — 1 call per run  
**Default model**: `sonnet` / `deepseek-chat`

### Pydantic output model

```python
class ContagionLink(BaseModel):
    source: str
    target: str
    lag_hours: int
    confidence: float

class GrangerLead(BaseModel):
    feature: str
    target_return: str      # "1d" | "5d"
    p_value: float

class ResearchContext(BaseModel):
    dominant_theme: str
    contagion_links: list[ContagionLink]
    squeeze_risk_tickers: list[str]
    granger_leads: list[GrangerLead]
    regime_note: str
```

### Node implementation

```python
def research_node(state: GraphState) -> dict:
    # Code pre-work: run research modules, collect quantitative outputs
    contagion = _run_sector_contagion(state["flagged_signals"])
    squeeze   = _run_gamma_squeeze(state["flagged_signals"])
    granger   = _run_granger(state["flagged_signals"])
    regime    = _get_regime(state["scored_batches"])

    # Build prompt context from quantitative outputs
    prompt = _build_research_prompt(
        state["flagged_signals"][:10],   # cap context size
        contagion, squeeze, granger, regime
    )

    # LLM call with structured output — no JSON parsing
    alias = state["model_aliases"].get("research", "sonnet")
    llm   = get_agent_model("research", override=alias)
    result: ResearchContext = llm.with_structured_output(ResearchContext).invoke(prompt)

    return {"research_context": result.model_dump()}
```

### DeepSeek-chat as an alternative

`deepseek-chat` is a strong option for `research_node` — it handles structured
JSON extraction well and costs ~80% less than Sonnet. Set `RESEARCH_MODEL=deepseek-chat`
to route this node there without any code changes.

---

## 3.6 — strategy_node

**File**: `agents/graph/nodes/strategy_node.py`  
**Type**: LLM — 1 call per flagged signal (fan-out via `Send`)  
**Default model**: `sonnet` / `deepseek-chat`

### Pydantic output model

```python
class PositionSizing(BaseModel):
    kelly_fraction: float
    recommended_pct: str        # e.g. "2.0%"
    max_contracts: int

class TradeParams(BaseModel):
    ticker: str
    direction: Literal["CALL", "PUT"]
    entry_condition: str
    strike_preference: str
    dte_target: str
    position_sizing: PositionSizing
    stop_loss: str
    profit_target: str
    hedges: str
    rationale: str
    conviction_score: float
    signal_id: str
```

### Node implementation

Each invocation receives a single signal (from `Send` fan-out):

```python
def strategy_node(state: dict) -> dict:
    # state here is the per-signal slice sent by route_to_strategy()
    signal          = state["signal"]
    research_ctx    = state["research_context"]
    alias           = state.get("model_alias", "sonnet")

    kelly = _compute_kelly(signal)
    prompt = _build_strategy_prompt(signal, research_ctx, kelly)

    llm    = get_agent_model("strategy", override=alias)
    result: TradeParams = llm.with_structured_output(TradeParams).invoke(prompt)

    return {"trade_params": [result.model_dump()]}   # list for operator.add accumulation
```

### DeepSeek-R1 for complex sizing

For signals where position sizing or hedge logic is especially nuanced
(e.g. high vega + low IV Rank + gamma squeeze risk simultaneously),
`deepseek-r1` can be used as an override — its chain-of-thought reasoning
produces more careful position size calculations. This is an on-demand
override, not the default.

---

## 3.7 — synthesis_node

**File**: `agents/graph/nodes/synthesis_node.py`  
**Type**: LLM — 1 call per run  
**Default model**: `sonnet`

### Pydantic output model

```python
class SetupSummary(BaseModel):
    ticker: str
    direction: str
    thesis: str
    key_risk: str

class DailyBrief(BaseModel):
    regime_summary: str
    top_3_setups: list[SetupSummary]
    macro_risk_flags: list[str]
    sector_rotation: str
    daily_narrative: str          # 2-3 sentences
```

### Node implementation

```python
def synthesis_node(state: GraphState) -> dict:
    if not state.get("trade_params"):
        return {"daily_brief": _empty_brief(state["target_date"])}

    prompt = _build_synthesis_prompt(
        state["target_date"],
        state["trade_params"],
        state["research_context"],
    )

    alias = state["model_aliases"].get("synthesis", "sonnet")
    llm   = get_agent_model("synthesis", override=alias)
    result: DailyBrief = llm.with_structured_output(DailyBrief).invoke(prompt)

    return {"daily_brief": result.model_dump()}
```

---

## 3.8 — persist_node

**File**: `agents/graph/nodes/persist_node.py`  
**Type**: Code only — writes all outputs to QuestDB

```python
def persist_node(state: GraphState) -> dict:
    _write_trade_params(state["trade_params"])
    _write_daily_brief(state["daily_brief"], state["target_date"])
    # scored_batches already persisted by ConvictionScorer if configured
    return {}   # no state updates — side effects only
```

---

## 3.9 — end_early_node

**File**: `agents/graph/nodes/end_early.py`  
**Type**: Code only — logs and exits cleanly

```python
def end_early_node(state: GraphState) -> dict:
    import logging
    log = logging.getLogger(__name__)
    for err in state.get("errors", []):
        log.error("Graph ended early: %s", err)
    return {}
```

---

## 3.10 — Prompt Design Principles

All prompts follow the same three-part structure:

```
[SYSTEM]
You are a [role]. Return ONLY valid structured output matching the schema.
Never include explanations, markdown, or keys not in the schema.

[CONTEXT BLOCK]
Structured quantitative inputs (JSON from ML pipeline):
  - Signal details
  - Research context
  - Risk config / regime

[INSTRUCTION]
"Produce a [OutputModel name] with these exact fields: ..."
```

This is intentionally brief — the LLM's job is *synthesis and translation*,
not reasoning from scratch. The heavy quantitative work happens in code nodes.

---

## Phase 3 Deliverables

- [ ] All 8 node files under `agents/graph/nodes/`
- [ ] `ResearchContext`, `TradeParams`, `DailyBrief` Pydantic models
  (in `agents/graph/models.py`)
- [ ] Prompt builder functions (in `agents/graph/prompts.py`)
- [ ] Kelly fraction helper (`_compute_kelly`)
- [ ] `persist_node` wiring to existing QDB ILP writers
- [ ] Integration test: full graph run on one symbol, `dry_run=True`

## Commit checkpoints (per node)

```
feat(agents/phase3): budget_check + data_node + ml_node (code-only nodes)
feat(agents/phase3): research_node — ResearchContext structured output
feat(agents/phase3): strategy_node — TradeParams + Send fan-out
feat(agents/phase3): synthesis_node — DailyBrief + persist_node
```
