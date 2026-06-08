# Multi-Agent Options Analysis — Design Plan

**Branch**: `multi_agentic_analysis`  
**Goal**: Replace the single-threaded LLM enrichment loop with a coordinated multi-agent
pipeline that analyzes, prepares, and queries data across the full ML stack —
model-agnostic, cost-tracked, idempotent.

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

## Architecture

```
                    ┌─────────────────────────────┐
                    │      CoordinatorAgent        │
                    │  routes work, sets budget,   │
                    │  resolves model aliases      │
                    └──────┬───────────────┬───────┘
                           │               │
           ┌───────────────┘               └──────────────────┐
           ▼                                                   ▼
   ┌───────────────┐                               ┌──────────────────┐
   │  DataAgent    │                               │  ResearchAgent   │
   │  (code only)  │                               │  (mid-tier LLM)  │
   │  QuestDB →    │                               │  Granger, GEX,   │
   │  60+ features │                               │  contagion,      │
   └──────┬────────┘                               │  HDBSCAN cluster │
          │ SignalBatch                             └────────┬─────────┘
          ▼                                                 │ ResearchContext
   ┌───────────────┐                                        │
   │   MLAgent     │──────────────────────────────────────▶│
   │  (code only)  │                                        ▼
   │  ConvictionScorer                          ┌────────────────────┐
   │  SHAP values  │                            │   StrategyAgent    │
   └───────────────┘                            │  (mid-tier LLM)    │
                                                │  per-signal trade  │
                                                │  params + sizing   │
                                                └──────────┬─────────┘
                                                           │ TradeParams[]
                                                           ▼
                                                 ┌──────────────────┐
                                                 │  SynthesisAgent  │
                                                 │  (full-tier LLM) │
                                                 │  cross-symbol    │
                                                 │  daily brief     │
                                                 └──────────────────┘
```

### Agent Roles

| Agent | Model Tier | LLM calls/day | Primary job |
|---|---|---|---|
| CoordinatorAgent | Fast (Haiku / GPT-4o-mini) | 1 | Route, budget gate, context injection |
| DataAgent | None (code) | 0 | QuestDB → feature matrix → signal ranking |
| MLAgent | None (code) | 0 | ConvictionScorer → SHAP → walk-forward hit rate |
| ResearchAgent | Mid (Sonnet / GPT-4o) | 1 | Granger + contagion + squeeze → ResearchContext |
| StrategyAgent | Mid (Sonnet / GPT-4o) | 5–15 | Per-signal TradeParams |
| SynthesisAgent | Full (Sonnet / Opus) | 1 | Cross-symbol daily brief |

---

## Step 1 — Model-Agnostic LLM Backend

**New file**: `app/modules/llm/backends.py`

Define a `LLMBackend` Protocol — any provider implementing it can be dropped in
without changing any agent code.

```python
@dataclass
class LLMResponse:
    text: str
    input_tokens: int
    output_tokens: int
    model: str
    provider: str

class LLMBackend(Protocol):
    provider: str
    def complete(
        self,
        messages: list[dict],   # [{"role": "user"|"assistant", "content": "..."}]
        model: str,
        max_tokens: int,
        temperature: float = 0.0,
        system: str | None = None,
    ) -> LLMResponse: ...
```

**Backends to implement**:

| Class | Provider | Key env var |
|---|---|---|
| `AnthropicBackend` | Claude (Haiku / Sonnet / Opus) | `ANTHROPIC_API_KEY` |
| `OpenAIBackend` | GPT-4o, GPT-4o-mini, o1 | `OPENAI_API_KEY` |
| `GeminiBackend` | Gemini 2.0 Flash, 2.5 Pro | `GEMINI_API_KEY` |
| `OllamaBackend` | Llama 3.3, Mistral (local) | `OLLAMA_HOST` (no key) |

**New file**: `app/modules/llm/model_registry.py`

```python
MODEL_REGISTRY = {
    # alias          provider      model_id
    "haiku":       ("anthropic", "claude-haiku-4-5-20251001"),
    "sonnet":      ("anthropic", "claude-sonnet-4-6"),
    "opus":        ("anthropic", "claude-opus-4-8"),
    "gpt-4o-mini": ("openai",   "gpt-4o-mini"),
    "gpt-4o":      ("openai",   "gpt-4o"),
    "gemini-flash":("gemini",   "gemini-2.0-flash"),
    "gemini-pro":  ("gemini",   "gemini-2.5-pro"),
    "llama3":      ("ollama",   "llama3.3:70b"),
}

def get_backend(alias: str) -> tuple[LLMBackend, str]:
    """Return (backend_instance, model_id) for a given alias."""
```

**Updated `LLMClient`**: accepts a `backend` argument (defaults to `AnthropicBackend`
for backwards compatibility). Audit log gains a `provider SYMBOL` column.

---

## Step 2 — Agent Base Class

**New file**: `app/modules/agents/base_agent.py`

```python
@dataclass
class AgentContext:
    run_id: str
    target_date: str
    symbols: list[str]
    budget_remaining_usd: float
    metadata: dict = field(default_factory=dict)

class BaseAgent(ABC):
    name: str                     # used in audit log
    default_model_alias: str      # e.g. "haiku", "sonnet"

    def __init__(self, model_alias: str | None = None):
        self.model_alias = model_alias or os.getenv(
            f"{self.name.upper()}_MODEL", self.default_model_alias
        )

    @abstractmethod
    def run(self, ctx: AgentContext, **inputs) -> dict: ...

    def _llm(self, messages, system=None, max_tokens=500) -> str:
        backend, model_id = get_backend(self.model_alias)
        resp = backend.complete(messages=messages, model=model_id,
                                max_tokens=max_tokens, system=system)
        _write_agent_run_log(self.name, resp)   # agent_run_log table
        return resp.text
```

All agents:
- **Idempotent**: check existing results before running LLM calls
- **Budget-aware**: raise `BudgetExceededError` if `ctx.budget_remaining_usd < 0.01`
- **Structured output**: return typed Python dicts, parse JSON from LLM responses

---

## Step 3 — Agent Implementations

### 3.1 DataAgent

**File**: `app/modules/agents/data_agent.py`  
**No LLM calls** — pure Python + SQL.

```
Inputs:  ctx (symbols, date_range, min_premium)
Process:
  1. query signal_catalog for all events in date_range (labeled or unlabeled)
  2. call load_training_data() → full feature matrix per symbol
  3. rank signals by composite score:
       raw_score = volume_ratio_20d × log_premium_total × (1 + iv_rank/100)
  4. cluster by (symbol, dte_bucket, otm_pct) using HDBSCAN fingerprinting
  5. tag each event with its cluster archetype + historical cluster hit rate

Output: SignalBatch {
    signals: list[dict],           # all feature vectors
    clusters: dict[str, list],     # cluster_id → signal_ids
    ranked_ids: list[str],         # signal_id sorted by raw_score desc
    feature_matrix: pd.DataFrame,  # full matrix for MLAgent
}
```

### 3.2 MLAgent

**File**: `app/modules/agents/ml_agent.py`  
**No LLM calls** — runs the existing model stack.

```
Inputs:  SignalBatch from DataAgent
Process:
  1. score each signal through ConvictionScorer (quality × direction × magnitude × regime)
  2. compute SHAP values for top-20 by conviction_score
  3. look up walk-forward backtest hit rate for signals in same cluster (30d window)
  4. flag signals where conviction_score > 0.65 AND cluster_hit_rate > 0.55

Output: ScoredBatch {
    scored: list[ScoredSignal],   # all signals with component scores
    flagged: list[ScoredSignal],  # only those above both thresholds
    shap_summaries: dict,         # top-3 features per flagged signal
}
```

### 3.3 ResearchAgent

**File**: `app/modules/agents/research_agent.py`  
**1 LLM call** — mid-tier model (Sonnet / GPT-4o).

```
Inputs:  ScoredBatch, regime features (vix_level, spy_return_5d, ...)
Code pre-work (before LLM):
  1. sector_contagion.py → cross-ticker lag correlations at 1h, 2h, 4h
  2. gamma_squeeze_detect.py → squeeze score per flagged ticker
  3. granger_causality.py → which flow features Granger-cause returns (p < 0.05)

LLM prompt context injected:
  - top-5 flagged signals (symbol, conviction_score, SHAP top-3 features)
  - contagion map (NVDA → AMD 1h lag, r=0.72 ...)
  - squeeze scores per ticker
  - Granger-significant variables + p-values
  - current regime (regime_model.predict_regime())

LLM structured output:
{
  "dominant_theme": "Semiconductor bullish accumulation",
  "contagion_links": [{"source":"NVDA","target":"AMD","lag_h":1,"confidence":0.72}],
  "squeeze_risk_tickers": ["NVDA"],
  "granger_leads": [{"feature":"net_call_premium","target":"5d_return","p":0.003}],
  "regime_note": "Trending bull, regime_multiplier=1.2 supports long bias"
}
```

### 3.4 StrategyAgent

**File**: `app/modules/agents/strategy_agent.py`  
**1 LLM call per flagged signal** — mid-tier model.

```
Inputs:  one ScoredSignal, ResearchContext, iv_surface for that ticker
LLM prompt includes:
  - signal details (symbol, strike, DTE, IV Rank, conviction breakdown)
  - SHAP top features explaining the score
  - ResearchContext (regime note, contagion links, squeeze risk)
  - risk config (max position size, stop-loss policy)
  - current Greeks at that strike

LLM structured output per signal:
{
  "ticker": "NVDA",
  "direction": "CALL",
  "entry_condition": "break above $880 intraday on volume > 1.5x RVOL",
  "strike_preference": "$880–$900 calls, ATM to 2.5% OTM",
  "dte_target": "10–14 days (minimize theta decay risk)",
  "position_sizing": {
    "kelly_fraction": 0.23,
    "recommended_pct": "2.0% of portfolio",
    "max_contracts": 5
  },
  "stop_loss": "exit at 50% premium loss (~$X)",
  "profit_target": "exit at 100% gain OR close 3 days before expiry",
  "hedges": "buy 1 SPY $450 put if conviction < 0.7 at entry",
  "rationale": "..."
}
```

### 3.5 SynthesisAgent

**File**: `app/modules/agents/synthesis_agent.py`  
**1 LLM call per day** — full-tier model.

```
Inputs:  all TradeParams[], ResearchContext, prior_day_outcomes (from signal_catalog)
LLM prompt context:
  - all flagged signals grouped by regime bucket
  - prior 5-day outcomes for same-ticker same-archetype signals
  - macro flags (GLD/TLT unusual volume, SPY PCR)
  - top SHAP features across all signals

LLM structured output:
{
  "regime_summary": "Bull trending (regime_mult=1.2), VIX at 25th pct — conditions favor calls",
  "top_3_setups": [
    { "ticker":"NVDA", "thesis":"...", "key_risk":"..." },
    { "ticker":"AMD",  "thesis":"...", "key_risk":"..." },
    { "ticker":"SPY",  "thesis":"...", "key_risk":"..." }
  ],
  "macro_risk_flags": ["TLT unusual call volume at 4.1× — rate cut positioning"],
  "sector_rotation": "Semis rotating into MAG7 broad tech, watch AMZN/MSFT for follow-through",
  "daily_narrative": "2-3 sentences a trader reads first thing"
}
→ written to daily_briefs table, surfaced in Angular dashboard
```

---

## Step 4 — Prefect Multi-Agent Orchestration Flow

**File**: `app/modules/agents/flows/multi_agent_analysis_flow.py`

```python
@flow(name="multi_agent_options_analysis")
def multi_agent_analysis_flow(
    symbols: list[str] | None = None,
    target_date: str | None = None,
    model_aliases: dict | None = None,  # {"research": "gpt-4o", "strategy": "sonnet"}
    dry_run: bool = False,
) -> dict:
    d = target_date or str(date.today() - timedelta(days=1))
    syms = symbols or WATCHLIST

    # 1. Budget gate (same BudgetExceededError pattern as enrichment_flow)
    budget = check_llm_budget_task()

    # 2. DataAgent: code-only, parallel per symbol
    batches = [data_agent_task(sym, d) for sym in syms]
    merged_batch = merge_signal_batches(batches)

    # 3. MLAgent: code-only, scores full merged batch
    scored = ml_agent_task(merged_batch)

    # 4. ResearchAgent: 1 LLM call, all symbols merged
    research = research_agent_task(
        scored, model_alias=model_aliases.get("research", "sonnet")
    )

    # 5. StrategyAgent: parallel per flagged signal
    trade_params = [
        strategy_agent_task(sig, research, model_alias=model_aliases.get("strategy", "sonnet"))
        for sig in scored.flagged
    ]

    # 6. SynthesisAgent: 1 LLM call
    brief = synthesis_agent_task(
        trade_params, research, model_alias=model_aliases.get("synthesis", "sonnet")
    )

    # 7. Persist
    persist_agent_results(scored, research, trade_params, brief, d)

    return {"brief": brief, "trade_params_count": len(trade_params)}
```

**Schedule**: 22:45 ET daily (after feature computation at 22:30).  
**On-demand**: `POST /api/v1/agents/analyze` → triggers flow, returns `flow_run_id`.

---

## Step 5 — Database Schema

### New QuestDB tables

```sql
-- One row per agent invocation (provider-agnostic audit)
CREATE TABLE agent_run_log (
    run_at        TIMESTAMP,
    flow_run_id   STRING,
    agent_name    SYMBOL,
    symbol        SYMBOL,
    model_alias   SYMBOL,
    provider      SYMBOL,
    model_id      SYMBOL,
    input_tokens  INT,
    output_tokens INT,
    cost_usd      DOUBLE,
    latency_ms    INT,
    status        SYMBOL,
    error_msg     STRING
) TIMESTAMP(run_at) PARTITION BY MONTH;

-- SynthesisAgent daily brief
CREATE TABLE daily_briefs (
    brief_at          TIMESTAMP,
    target_date       DATE,
    regime_summary    STRING,
    top_setups_json   STRING,
    macro_risks_json  STRING,
    daily_narrative   STRING,
    provider          SYMBOL,
    model_id          SYMBOL,
    cost_usd          DOUBLE
) TIMESTAMP(brief_at) PARTITION BY MONTH;

-- StrategyAgent per-signal trade parameters
CREATE TABLE agent_trade_params (
    generated_at     TIMESTAMP,
    signal_id        STRING,
    symbol           SYMBOL,
    direction        SYMBOL,
    conviction_score DOUBLE,
    params_json      STRING,
    provider         SYMBOL,
    model_id         SYMBOL
) TIMESTAMP(generated_at) PARTITION BY MONTH;
```

### Update `llm_audit_log`

Add `provider SYMBOL` column to distinguish per-call which backend was used.

---

## Step 6 — API Endpoints

**File**: `app/modules/agents/api/agent_api.py`

```
POST /api/v1/agents/analyze
  Body: { symbols?, target_date?, model_aliases?, dry_run? }
  → triggers multi_agent_analysis_flow, returns { flow_run_id }

GET  /api/v1/agents/brief/{date}
  → daily_briefs row for that date (DailyBrief JSON)

GET  /api/v1/agents/trade-params/{date}?symbol=NVDA
  → agent_trade_params rows filtered by date + optional symbol

GET  /api/v1/agents/run-log?limit=50
  → agent_run_log, paginated — powers observability dashboard
```

---

## Step 7 — Model-Agnostic Configuration

Switch providers entirely via environment variables — zero code changes:

```bash
# Per-agent model alias (keys from MODEL_REGISTRY)
COORDINATOR_MODEL=haiku
RESEARCH_MODEL=sonnet
STRATEGY_MODEL=sonnet
SYNTHESIS_MODEL=sonnet

# Provider API keys (only the provider(s) you're using)
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
GEMINI_API_KEY=AIza...

# Local models via Ollama (no key, zero cost)
OLLAMA_HOST=http://localhost:11434
```

To run entirely on GPT-4o:
```bash
RESEARCH_MODEL=gpt-4o STRATEGY_MODEL=gpt-4o SYNTHESIS_MODEL=gpt-4o
```

To run cost-free with local models:
```bash
RESEARCH_MODEL=llama3 STRATEGY_MODEL=llama3 SYNTHESIS_MODEL=llama3
```

---

## Implementation Sequence

| Step | What | Files created | Depends on |
|---|---|---|---|
| 1a | `LLMBackend` Protocol + `LLMResponse` | `llm/backends.py` | Nothing |
| 1b | `MODEL_REGISTRY` + `get_backend()` | `llm/model_registry.py` | Step 1a |
| 1c | `AnthropicBackend` (existing behavior, new interface) | `llm/backends.py` | Step 1a |
| 1d | `OpenAIBackend`, `GeminiBackend`, `OllamaBackend` | `llm/backends.py` | Step 1c |
| 1e | Update `LLMClient.create()` to accept backend | `llm/audit.py` | Step 1b |
| 2 | `BaseAgent` + `AgentContext` | `agents/base_agent.py` | Step 1e |
| 3a | `DataAgent` | `agents/data_agent.py` | Step 2 + existing feature builder |
| 3b | `MLAgent` | `agents/ml_agent.py` | Step 2 + existing ConvictionScorer |
| 3c | `ResearchAgent` | `agents/research_agent.py` | Steps 3a, 3b + research modules |
| 3d | `StrategyAgent` | `agents/strategy_agent.py` | Steps 3a–3c |
| 3e | `SynthesisAgent` | `agents/synthesis_agent.py` | Steps 3a–3d |
| 4 | Prefect orchestration flow | `agents/flows/multi_agent_analysis_flow.py` | Steps 3a–3e |
| 5 | DB schema + `agents/db/schema.py` | `agents/db/schema.py` | Step 4 |
| 6 | API endpoints + router wiring | `agents/api/agent_api.py` | Step 5 |

Steps 3a + 3b are independent (both code-only) — build in parallel.  
Steps 3c + 3d are independent — build in parallel after 3a + 3b land.

---

## Cost Estimate

| Agent | Model | Calls/day | ~Tokens/call | Est. cost/day |
|---|---|---|---|---|
| CoordinatorAgent | Haiku | 1 | 500 in + 200 out | $0.0005 |
| ResearchAgent | Sonnet | 1 | 2,000 in + 500 out | ~$0.020 |
| StrategyAgent | Sonnet | 10 signals avg | 1,500 in + 400 out | ~$0.22 |
| SynthesisAgent | Sonnet | 1 | 3,000 in + 600 out | ~$0.025 |
| **Total** | | | | **~$0.27/day** |

Fits comfortably within the existing $2.27/day daily budget cap alongside the
original Haiku enrichment (~$0.02/day).

---

## Open Questions (resolve before implementing Step 3c)

1. **Kelly sizing**: full Kelly or fractional (½ Kelly)? Production standard is ½ Kelly.
2. **Human approval gate**: should `TradeParams` write to the Angular dashboard immediately,
   or wait for a human `POST /api/v1/agents/trade-params/{id}/approve`?
3. **Ollama availability**: is there a local GPU machine, or is this cloud-only for the
   initial version?
4. **ResearchAgent threshold**: run on signals with conviction > 0.50, or only top-N by
   premium_total? Recommend top-10 by premium to control LLM context size.
