"""
TOPIC_REGISTRY — comprehensive index of explainer topics for the education agent.

Each entry maps a slug to:
  title:        human-readable heading shown in the Angular /docs section
  category:     groups topics in the UI sidebar
  description:  what this topic explains (used for LLM system prompt framing)
  source_files: paths relative to python-service/ that the LLM will read as context
  audience:     one sentence about the assumed reader (used in prompt)

Topics are ordered for a progressive reading path within each category.
The education agent works through them in order, one per on-demand request,
skipping topics that already have a stored explainer in QuestDB.
"""
from __future__ import annotations

TOPIC_REGISTRY: dict[str, dict] = {

    # ── System Overview ───────────────────────────────────────────────────────
    "system-overview": {
        "title":       "What this system does — end-to-end pipeline overview",
        "category":    "System Overview",
        "description": (
            "A plain-English walkthrough of the entire MarketAI platform: what data "
            "comes in, what each service does with it, and what comes out the other end. "
            "Covers the Angular → NestJS → Python → QuestDB data flow and where Go fits in."
        ),
        "source_files": ["app/modules/agents/graph/analysis_graph.py",
                         "app/modules/agents/graph/state.py"],
        "audience":    "programmer new to the project, reading the codebase for the first time",
    },

    "signal-what-is-it": {
        "title":       "What a 'signal' is in this codebase",
        "category":    "System Overview",
        "description": (
            "Defines what the word 'signal' means throughout this project: an options "
            "contract with statistically unusual volume on a given day. Explains why "
            "unusual volume matters, how signals are detected, and how they travel "
            "from raw data through scoring to trade recommendations."
        ),
        "source_files": ["app/modules/agents/data_agent.py",
                         "app/modules/agents/ml_agent.py"],
        "audience":    "programmer unfamiliar with options or quantitative finance",
    },

    # ── Options Fundamentals ──────────────────────────────────────────────────
    "options-call-put": {
        "title":       "CALL and PUT options — what they are and when each is used",
        "category":    "Options Fundamentals",
        "description": (
            "Explains what an options contract is, what CALL and PUT mean, "
            "and when a trader buys each. Uses concrete ticker examples. "
            "No prior knowledge of derivatives assumed."
        ),
        "source_files": ["app/modules/agents/graph/models.py",
                         "app/modules/agents/graph/nodes/strategy_node.py"],
        "audience":    "programmer who has never traded options",
    },

    "options-dte": {
        "title":       "DTE — days to expiration and how time decay works",
        "category":    "Options Fundamentals",
        "description": (
            "Explains DTE (days to expiration), theta (time decay), and why "
            "the system tracks DTE buckets as a clustering feature. "
            "Why buying a 7-DTE option is very different from a 60-DTE option."
        ),
        "source_files": ["app/modules/agents/graph/models.py",
                         "app/modules/agents/graph/nodes/strategy_node.py"],
        "audience":    "programmer who understands what options are but not time decay",
    },

    "options-otm-pct": {
        "title":       "OTM% — out-of-the-money percentage and strike selection",
        "category":    "Options Fundamentals",
        "description": (
            "Explains what out-of-the-money means for both calls and puts, "
            "how OTM% is calculated, and why the system uses it to fingerprint "
            "signal clusters. Includes concrete examples with real numbers."
        ),
        "source_files": ["app/modules/agents/data_agent.py"],
        "audience":    "programmer who knows what options are but not strike terminology",
    },

    "options-iv-rank": {
        "title":       "IV rank — implied volatility rank and what it signals",
        "category":    "Options Fundamentals",
        "description": (
            "Explains implied volatility (IV), how IV rank normalises it to a 0–100 "
            "percentile, and why high IV rank makes buying options expensive. "
            "Why the system uses it as a feature rather than raw IV."
        ),
        "source_files": ["app/modules/agents/graph/nodes/strategy_node.py",
                         "app/modules/agents/data_agent.py"],
        "audience":    "programmer unfamiliar with options pricing",
    },

    "options-premium": {
        "title":       "Premium — what you pay for an option and why it matters",
        "category":    "Options Fundamentals",
        "description": (
            "Explains options premium, why a large premium on an unusual-volume "
            "contract is a strong signal of informed buying, and how "
            "premium_total is used as a filter in this codebase."
        ),
        "source_files": ["app/modules/agents/data_agent.py"],
        "audience":    "programmer unfamiliar with options pricing",
    },

    "options-greeks": {
        "title":       "Options Greeks — delta, gamma, vega, theta in plain English",
        "category":    "Options Fundamentals",
        "description": (
            "Explains the four primary Greeks. Focuses on gamma (curvature, "
            "why it causes gamma squeezes) and vega (sensitivity to IV, "
            "why the system flags high-vega signals for hedges)."
        ),
        "source_files": ["app/modules/agents/graph/nodes/strategy_node.py",
                         "app/modules/agents/graph/nodes/research_node.py"],
        "audience":    "programmer who knows what options are but not the Greeks",
    },

    # ── ML Pipeline ───────────────────────────────────────────────────────────
    "ml-feature-engineering": {
        "title":       "Feature engineering — the 60+ feature matrix explained",
        "category":    "ML Pipeline",
        "description": (
            "Explains what 'features' are in machine learning, then walks through "
            "the four feature groups built by tos_feature_builder: volume anomaly, "
            "price/IV context, cluster fingerprint, and historical performance. "
            "Why each group exists and what it contributes to the model."
        ),
        "source_files": ["app/modules/tos/ml/features/tos_feature_builder.py",
                         "app/modules/agents/data_agent.py"],
        "audience":    "programmer new to machine learning",
    },

    "ml-what-is-a-model": {
        "title":       "What a machine learning model is — and what it isn't",
        "category":    "ML Pipeline",
        "description": (
            "Plain-English explanation of what a trained model does: it maps a "
            "feature vector to a probability or score. Why this system uses "
            "multiple narrow models (quality, direction, magnitude, regime) "
            "rather than one big model."
        ),
        "source_files": ["app/modules/tos/ml/models/signal_quality_model.py",
                         "app/modules/tos/ml/models/direction_model.py",
                         "app/modules/tos/ml/models/magnitude_model.py"],
        "audience":    "programmer who has never trained a machine learning model",
    },

    "ml-conviction-scorer": {
        "title":       "ConvictionScorer — quality × direction × magnitude × regime",
        "category":    "ML Pipeline",
        "description": (
            "Full explanation of the ConvictionScorer formula: how four sub-scores "
            "are multiplied together, what each sub-score measures, why multiplication "
            "rather than addition, and how the regime multiplier can veto a strong signal. "
            "Includes worked examples with real numbers."
        ),
        "source_files": ["app/modules/tos/ml/inference/conviction_scorer.py",
                         "app/modules/agents/ml_agent.py"],
        "audience":    "programmer new to multi-factor scoring models",
    },

    "ml-shap-values": {
        "title":       "SHAP values — how to read feature importance in this codebase",
        "category":    "ML Pipeline",
        "description": (
            "Explains what SHAP is (SHapley Additive exPlanations), how it attributes "
            "a model's prediction to individual features, and how to read the "
            "shap_top3 field that appears on every scored signal. "
            "Concrete example: 'volume_ratio_20d pushed the score up by 0.12'."
        ),
        "source_files": ["app/modules/agents/ml_agent.py",
                         "app/modules/tos/ml/inference/conviction_scorer.py"],
        "audience":    "programmer who has used ML models but never looked at SHAP",
    },

    "ml-walk-forward-cv": {
        "title":       "Walk-forward cross-validation — why it replaces k-fold here",
        "category":    "ML Pipeline",
        "description": (
            "Explains the fundamental problem with k-fold cross-validation on time-series "
            "data (future leakage), and how walk-forward CV fixes it. "
            "How the nightly_retrain_flow.py uses it, and what min_labeled_days controls."
        ),
        "source_files": ["app/modules/tos/flows/nightly_retrain_flow.py",
                         "app/modules/tos/ml/features/tos_feature_builder.py"],
        "audience":    "programmer familiar with cross-validation but not time-series pitfalls",
    },

    "ml-hdbscan-clustering": {
        "title":       "HDBSCAN clustering — how signals are grouped by fingerprint",
        "category":    "ML Pipeline",
        "description": (
            "Explains what clustering does, why HDBSCAN is used instead of k-means, "
            "and what the (dte_bucket, otm_pct) fingerprint means for an options signal. "
            "How cluster_hit_rate is computed and why it gates the flagged_signals list."
        ),
        "source_files": ["app/modules/tos/ml/research/fingerprint_clustering.py",
                         "app/modules/agents/data_agent.py",
                         "app/modules/agents/ml_agent.py"],
        "audience":    "programmer who has heard of k-means but not density-based clustering",
    },

    "ml-regime-model": {
        "title":       "Market regimes — how the system detects bull/bear/neutral",
        "category":    "ML Pipeline",
        "description": (
            "Explains what a market regime is (macro context that changes how signals "
            "should be interpreted), how the regime_model classifies the current regime, "
            "and how the regime_multiplier can veto or amplify a conviction score."
        ),
        "source_files": ["app/modules/tos/ml/models/regime_model.py",
                         "app/modules/tos/ml/inference/conviction_scorer.py"],
        "audience":    "programmer unfamiliar with regime-based ML",
    },

    "ml-kelly-sizing": {
        "title":       "Half-Kelly position sizing — the formula and why we cap it",
        "category":    "ML Pipeline",
        "description": (
            "Derives the Kelly criterion from first principles (win probability, "
            "win/loss ratio), explains why full Kelly is too aggressive in practice, "
            "and walks through the half-Kelly implementation in strategy_node.py. "
            "What MAX_POSITION_PCT does and why it's the last line of defence."
        ),
        "source_files": ["app/modules/agents/graph/nodes/strategy_node.py"],
        "audience":    "programmer unfamiliar with position sizing formulas",
    },

    "ml-cluster-hit-rate": {
        "title":       "Cluster hit rate — tracking past signal success by archetype",
        "category":    "ML Pipeline",
        "description": (
            "Explains what cluster_hit_rate measures (fraction of past signals in "
            "the same dte_bucket+otm_pct cluster that reached the profit target), "
            "how it's computed from signal_catalog, and why both conviction_score "
            "AND cluster_hit_rate must exceed their thresholds to flag a signal."
        ),
        "source_files": ["app/modules/agents/ml_agent.py",
                         "app/modules/tos/ml/research/fingerprint_clustering.py"],
        "audience":    "programmer who understands conviction scoring but not the cluster gate",
    },

    # ── Research Modules ──────────────────────────────────────────────────────
    "research-unusual-volume": {
        "title":       "Unusual volume — why it predicts informed trading",
        "category":    "Research Modules",
        "description": (
            "Explains the academic and practical basis for using unusual options volume "
            "as a signal of informed buying. What volume_ratio_20d measures, why 20 days "
            "is the lookback window, and what a ratio of 10× actually means in practice."
        ),
        "source_files": ["app/modules/agents/data_agent.py",
                         "app/modules/tos/ml/features/tos_feature_builder.py"],
        "audience":    "programmer new to quantitative finance",
    },

    "research-sector-contagion": {
        "title":       "Sector contagion — detecting correlated moves across tickers",
        "category":    "Research Modules",
        "description": (
            "Explains what contagion means in a financial context (when a move in one "
            "ticker systematically predicts a move in another), how the sector_contagion "
            "module detects it, and what the ContagionLink output fields (source, target, "
            "lag_hours, confidence) mean for a research_node prompt."
        ),
        "source_files": ["app/modules/tos/ml/research/sector_contagion.py",
                         "app/modules/agents/graph/nodes/research_node.py"],
        "audience":    "programmer unfamiliar with correlated asset analysis",
    },

    "research-granger-causality": {
        "title":       "Granger causality — what 'leads' means and how it's tested",
        "category":    "Research Modules",
        "description": (
            "Explains the intuition behind Granger causality (can variable A's past "
            "values predict variable B better than B's own past?), why p-value < 0.05 "
            "is the threshold used, and what a GrangerLead with target_return='5d' "
            "means in practice."
        ),
        "source_files": ["app/modules/tos/ml/research/granger_causality.py",
                         "app/modules/agents/graph/nodes/research_node.py"],
        "audience":    "programmer who has heard of correlation but not Granger causality",
    },

    "research-gamma-squeeze": {
        "title":       "Gamma squeeze — what it is and how the scanner detects it",
        "category":    "Research Modules",
        "description": (
            "Explains what a gamma squeeze is (market makers forced to buy stock "
            "as options go in the money, creating a self-reinforcing rally), "
            "why gamma exposure is dangerous for market makers, and how "
            "gamma_squeeze_detect.py identifies tickers at risk."
        ),
        "source_files": ["app/modules/tos/ml/research/gamma_squeeze_detect.py",
                         "app/modules/agents/graph/nodes/research_node.py"],
        "audience":    "programmer who understands options basics but not market-maker dynamics",
    },

    # ── LangGraph ─────────────────────────────────────────────────────────────
    "langgraph-what-is-it": {
        "title":       "What LangGraph is — and how it differs from sequential code",
        "category":    "LangGraph",
        "description": (
            "Explains why LangGraph exists: the problem with writing multi-step "
            "LLM pipelines as plain Python (no observability, no branching, no "
            "resume-on-failure). What a StateGraph gives you that a for-loop doesn't."
        ),
        "source_files": ["app/modules/agents/graph/analysis_graph.py"],
        "audience":    "programmer who has written sequential LLM calls but never used a graph framework",
    },

    "langgraph-state": {
        "title":       "GraphState and TypedDict — how state flows between nodes",
        "category":    "LangGraph",
        "description": (
            "Explains the TypedDict pattern for shared state, how LangGraph merges "
            "partial dicts returned by each node, and why fields need to be "
            "defined upfront. Why there are no global variables in the nodes."
        ),
        "source_files": ["app/modules/agents/graph/state.py",
                         "app/modules/agents/graph/analysis_graph.py"],
        "audience":    "programmer new to LangGraph",
    },

    "langgraph-nodes-edges": {
        "title":       "Nodes, edges, and conditional edges — the three building blocks",
        "category":    "LangGraph",
        "description": (
            "What a node is (a plain Python function), what an edge is (a guaranteed "
            "transition), and what a conditional edge is (a routing function that "
            "picks the next node at runtime). Concrete examples from the budget_check "
            "and ml_node routing functions in this codebase."
        ),
        "source_files": ["app/modules/agents/graph/analysis_graph.py",
                         "app/modules/agents/graph/nodes/budget_check.py",
                         "app/modules/agents/graph/nodes/ml_node.py"],
        "audience":    "programmer new to LangGraph",
    },

    "langgraph-send-fanout": {
        "title":       "The Send API — how strategy_node runs once per flagged signal",
        "category":    "LangGraph",
        "description": (
            "Explains the LangGraph Send API: how route_to_strategy() returns a list "
            "of Send objects (one per flagged signal), how LangGraph spawns parallel "
            "executions of strategy_node, and why operator.add on trade_params is "
            "needed to accumulate results rather than overwrite them."
        ),
        "source_files": ["app/modules/agents/graph/analysis_graph.py",
                         "app/modules/agents/graph/state.py",
                         "app/modules/agents/graph/nodes/strategy_node.py"],
        "audience":    "programmer who understands LangGraph basics but not fan-out",
    },

    "langgraph-structured-output": {
        "title":       ".with_structured_output() — why it replaces JSON parsing",
        "category":    "LangGraph",
        "description": (
            "Explains what structured output means in LangGraph: the LLM is forced "
            "to return JSON matching a Pydantic model schema, validated at the "
            "framework level. Why this is better than asking the model to 'respond "
            "in JSON' and then parsing it with regex fallbacks."
        ),
        "source_files": ["app/modules/agents/graph/models.py",
                         "app/modules/agents/graph/nodes/research_node.py"],
        "audience":    "programmer who has used LLMs with raw text output",
    },

    "langgraph-streaming": {
        "title":       "graph.invoke() vs graph.astream() — sync and streaming execution",
        "category":    "LangGraph",
        "description": (
            "Explains the difference between invoke() (blocks until done) and "
            "astream() (yields chunks as each node completes). How the SSE endpoint "
            "uses astream() to push live node updates to the Angular dashboard. "
            "What stream_mode='updates' means and what each chunk contains."
        ),
        "source_files": ["app/modules/agents/api/agent_api.py",
                         "app/modules/agents/graph/analysis_graph.py"],
        "audience":    "programmer unfamiliar with async generators or SSE",
    },

    "langgraph-checkpointing": {
        "title":       "Checkpointing — saving graph state for resume and human review",
        "category":    "LangGraph",
        "description": (
            "Explains LangGraph checkpointers (MemorySaver for dev, PostgresSaver "
            "for production), what gets saved after each node, and how interrupt_after "
            "enables a human to review flagged signals before research_node runs. "
            "Why this is the architecture for human-in-the-loop."
        ),
        "source_files": ["app/modules/agents/graph/analysis_graph.py"],
        "audience":    "programmer who wants to add human review steps to the pipeline",
    },

    "langgraph-langsmith": {
        "title":       "LangSmith tracing — what gets captured automatically",
        "category":    "LangGraph",
        "description": (
            "Explains what LangSmith records for every graph.invoke(): the full prompt, "
            "the response, token counts, latency, cost estimate, and the graph path taken. "
            "Why LANGCHAIN_TRACING_V2=true is sufficient — no audit code in nodes. "
            "What to look for in the LangSmith UI when a run goes wrong."
        ),
        "source_files": ["app/modules/llm/model_factory.py",
                         "app/modules/agents/flows/multi_agent_analysis_flow.py"],
        "audience":    "programmer setting up LangSmith for the first time",
    },

    "langgraph-callbacks": {
        "title":       "RunnableConfig and callbacks — how QDBCostCallback is attached",
        "category":    "LangGraph",
        "description": (
            "Explains how LangChain's callback system works: BaseCallbackHandler "
            "hooks, on_llm_end, and how a RunnableConfig passes callbacks into a "
            "graph run without modifying any node code. Why QDBCostCallback is "
            "fire-and-forget and what happens if it fails."
        ),
        "source_files": ["app/modules/llm/qdb_callback.py",
                         "app/modules/agents/flows/multi_agent_analysis_flow.py"],
        "audience":    "programmer adding instrumentation to a LangGraph pipeline",
    },

    # ── Prefect ───────────────────────────────────────────────────────────────
    "prefect-what-is-it": {
        "title":       "What Prefect is — and how it differs from LangGraph",
        "category":    "Prefect",
        "description": (
            "Explains Prefect's role (scheduler + retry layer + observability for "
            "data pipelines) versus LangGraph's role (execution engine for the "
            "agent graph). Why both are needed and how they compose: "
            "Prefect task calls graph.invoke()."
        ),
        "source_files": ["app/modules/agents/flows/multi_agent_analysis_flow.py",
                         "app/modules/agents/flows/archive_flow.py"],
        "audience":    "programmer who has never used an orchestration framework",
    },

    "prefect-flow-task": {
        "title":       "@flow and @task decorators — how Prefect wraps work",
        "category":    "Prefect",
        "description": (
            "Explains what the @flow and @task decorators do under the hood: "
            "how Prefect intercepts the function call, logs it to the UI, tracks "
            "run state, and enables retries. Why tasks should be small and flows "
            "should orchestrate them."
        ),
        "source_files": ["app/modules/agents/flows/multi_agent_analysis_flow.py"],
        "audience":    "programmer new to Prefect",
    },

    "prefect-retries": {
        "title":       "Retries and retry_delay_seconds — how failures are handled",
        "category":    "Prefect",
        "description": (
            "Explains how Prefect retries work, why retries=1 with retry_delay_seconds=120 "
            "is used for the LangGraph task, and which failures should never be retried "
            "(e.g. budget_exceeded). How Prefect distinguishes task failure from flow failure."
        ),
        "source_files": ["app/modules/agents/flows/multi_agent_analysis_flow.py"],
        "audience":    "programmer configuring failure handling for the first time",
    },

    "prefect-schedules": {
        "title":       "Prefect schedules and deployments — how nightly runs are registered",
        "category":    "Prefect",
        "description": (
            "Explains the Prefect deployment model: how a flow is registered with a "
            "schedule (22:45 ET for analysis, Sunday 00:00 ET for archive), what "
            "'work pools' and 'workers' are, and how POST /agents/analyze triggers "
            "an on-demand flow run via run_deployment()."
        ),
        "source_files": ["app/modules/agents/flows/multi_agent_analysis_flow.py",
                         "app/modules/agents/api/agent_api.py"],
        "audience":    "programmer deploying a Prefect flow for the first time",
    },

    # ── Architecture ──────────────────────────────────────────────────────────
    "arch-questdb": {
        "title":       "QuestDB — what makes it different from PostgreSQL for time series",
        "category":    "Architecture",
        "description": (
            "Explains the core QuestDB design: columnar storage, partitioning by time, "
            "SAMPLE BY for time-series aggregation, and why standard SQL databases "
            "are slow for this workload. How TIMESTAMP(ts) PARTITION BY MONTH "
            "changes query performance for signals with 60-day lookbacks."
        ),
        "source_files": ["app/modules/agents/graph/nodes/persist_node.py"],
        "audience":    "programmer who knows SQL but has never used a time-series database",
    },

    "arch-ilp-ingestion": {
        "title":       "ILP ingestion — how Python writes rows to QuestDB at high speed",
        "category":    "Architecture",
        "description": (
            "Explains the InfluxDB Line Protocol that QuestDB uses for fast writes: "
            "what Sender.from_conf() does, why ILP is faster than INSERT statements, "
            "what symbols vs columns mean in the questdb-py API, and why sender.flush() "
            "must be called inside a 'with' block."
        ),
        "source_files": ["app/modules/agents/graph/nodes/persist_node.py",
                         "app/modules/agents/archive/archive_graph.py"],
        "audience":    "programmer who has used SQL INSERT but not the QuestDB Python client",
    },

    "arch-sample-by": {
        "title":       "SAMPLE BY — QuestDB's time-series aggregation syntax",
        "category":    "Architecture",
        "description": (
            "Explains the SAMPLE BY clause unique to QuestDB: how 'SAMPLE BY 1h' "
            "automatically buckets rows into hour windows, why it's faster than "
            "GROUP BY on a timestamp column, and example queries used in this codebase."
        ),
        "source_files": ["app/modules/llm/budget_guard.py"],
        "audience":    "SQL developer new to QuestDB",
    },

    "arch-nestjs-gateway": {
        "title":       "NestJS as API gateway — why Python endpoints are proxied through it",
        "category":    "Architecture",
        "description": (
            "Explains the two-layer API design: NestJS (port 3000) handles auth, "
            "rate limiting, and Angular-facing routes; Python FastAPI (port 8000) "
            "owns ML and agent logic. Why proxying avoids duplicating middleware "
            "and what the proxy pattern looks like in code."
        ),
        "source_files": [],
        "audience":    "full-stack developer new to multi-service architectures",
    },

    "arch-sse-streaming": {
        "title":       "FastAPI SSE — how live node progress reaches the Angular dashboard",
        "category":    "Architecture",
        "description": (
            "Explains Server-Sent Events: a one-directional HTTP stream from server "
            "to browser. How the POST /agents/analyze/stream endpoint uses "
            "graph.astream() to emit one event per node completion, and how Angular "
            "would consume it with EventSource."
        ),
        "source_files": ["app/modules/agents/api/agent_api.py"],
        "audience":    "frontend developer unfamiliar with SSE",
    },

    "arch-model-factory": {
        "title":       "model_factory.py — one function, 12 models, 5 providers",
        "category":    "Architecture",
        "description": (
            "Explains the build_chat_model(alias) design: why every node resolves "
            "its model at runtime from an env var alias, how @lru_cache prevents "
            "duplicate instantiation, and how switching RESEARCH_MODEL=deepseek-chat "
            "reroutes all research_node calls without any code change."
        ),
        "source_files": ["app/modules/llm/model_factory.py"],
        "audience":    "programmer who hardcodes model names and wants a cleaner approach",
    },

    "arch-budget-guard": {
        "title":       "Budget guard — how daily and monthly spend limits are enforced",
        "category":    "Architecture",
        "description": (
            "Explains how budget_guard.py reads llm_audit_log from QuestDB to compute "
            "current spend, why it's called at the START of the graph (not per node), "
            "and how BudgetExceededError routes the graph to end_early before any "
            "LLM calls are made."
        ),
        "source_files": ["app/modules/llm/budget_guard.py",
                         "app/modules/agents/graph/nodes/budget_check.py",
                         "app/modules/agents/graph/analysis_graph.py"],
        "audience":    "programmer adding cost controls to an LLM pipeline",
    },

    "arch-cost-callback": {
        "title":       "QDBCostCallback — bridging LangSmith tracing and QuestDB budgets",
        "category":    "Architecture",
        "description": (
            "Explains why both LangSmith AND llm_audit_log are needed: LangSmith "
            "traces prompts/latency for debugging; llm_audit_log is what budget_guard "
            "reads to enforce caps. How QDBCostCallback fills the gap, and why "
            "fire-and-forget is the right failure mode for an audit callback."
        ),
        "source_files": ["app/modules/llm/qdb_callback.py",
                         "app/modules/llm/budget_guard.py"],
        "audience":    "programmer who has LangSmith set up and wonders why QuestDB also tracks cost",
    },
}


# Ordered list of slugs for progressive reading / round-robin scheduling
TOPIC_ORDER: list[str] = list(TOPIC_REGISTRY.keys())

CATEGORIES: list[str] = list(dict.fromkeys(
    v["category"] for v in TOPIC_REGISTRY.values()
))
