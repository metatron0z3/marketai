# Phase 1 — Foundation: Dependencies, Model Factory, LangSmith

## Goal

Install LangGraph and all provider packages, wire LangSmith tracing,
and build a `build_chat_model(alias)` factory that the graph nodes will use.
This replaces `llm/backends.py` and `llm/model_registry.py` from the current skeleton.

---

## 1.1 — Dependency Changes

### Add to `python-service/requirements.txt`

```
# LangGraph core
langgraph>=0.2
langchain-core>=0.3

# Provider packages — install only what you have API keys for
langchain-anthropic>=0.3
langchain-openai>=0.2          # covers OpenAI + DeepSeek (OpenAI-compat endpoint)
langchain-google-genai>=2.0    # Gemini
langchain-ollama>=0.2          # local Ollama models

# Observability
langsmith>=0.2
```

### Remove from `requirements.txt`

```
# These are replaced by the langchain provider packages:
# anthropic  ← now pulled in transitively by langchain-anthropic
```

Keep `anthropic` pinned if it's imported directly elsewhere (e.g. existing
`llm/audit.py` — see Phase 1.3 for the transition plan).

---

## 1.2 — Environment Variables

Add to `.env.example` and `docker-compose.yml` environment sections:

```bash
# LangSmith — observability (get key at smith.langchain.com)
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=ls__...
LANGCHAIN_PROJECT=marketai-options-analysis   # groups traces by project in the UI

# Provider keys (only those you're using)
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
GEMINI_API_KEY=AIza...
DEEPSEEK_API_KEY=sk-...       # deepseek.com → API keys

# DeepSeek endpoint (OpenAI-compatible, no extra package needed)
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1

# Local Ollama
OLLAMA_HOST=http://localhost:11434

# Agent-level model selection (alias from MODEL_REGISTRY in 01-model-factory)
COORDINATOR_MODEL=haiku
RESEARCH_MODEL=sonnet
STRATEGY_MODEL=sonnet
SYNTHESIS_MODEL=sonnet
```

---

## 1.3 — Transition Plan for `llm/audit.py`

The existing `LLMClient` wraps `anthropic.Anthropic` directly and writes to `llm_audit_log`.
LangSmith replaces its observability role for LangGraph nodes.

**Transition path** (keep both working during migration):

| Caller | During migration | After migration |
|---|---|---|
| `options/services/llm_enrichment.py` | Keep using `LLMClient` | Port to LangGraph node (Phase 3) |
| `options/flows/enrichment_flow.py` | Keep using Prefect + LLMClient | Keep (not replacing Prefect) |
| New LangGraph nodes | Use `build_chat_model()` — LangSmith traces automatically | — |

The `llm_audit_log` QuestDB table stays for the legacy enrichment flow.
New LangGraph calls are traced in LangSmith instead — two observability systems
in parallel until the legacy flow is fully migrated.

---

## 1.4 — Model Factory

**New file**: `python-service/app/modules/llm/model_factory.py`

This replaces the custom `LLMBackend` protocol from `backends.py` with LangChain's
`BaseChatModel`, which all provider packages implement natively.

```python
"""
build_chat_model(alias) → BaseChatModel

All LangGraph nodes call this factory. Switching providers requires only an
env var change — no code changes.

Supported aliases and their env var overrides:
  haiku, sonnet, opus                    → ANTHROPIC_API_KEY
  gpt-4o-mini, gpt-4o, o1               → OPENAI_API_KEY
  gemini-flash, gemini-pro               → GEMINI_API_KEY
  deepseek-chat, deepseek-r1             → DEEPSEEK_API_KEY + DEEPSEEK_BASE_URL
  llama3, mistral                        → OLLAMA_HOST (no key)
"""
import os
from functools import lru_cache
from langchain_core.language_models import BaseChatModel

MODEL_REGISTRY: dict[str, dict] = {
    # --- Anthropic ---
    "haiku": {
        "provider": "anthropic",
        "model":    "claude-haiku-4-5-20251001",
    },
    "sonnet": {
        "provider": "anthropic",
        "model":    "claude-sonnet-4-6",
    },
    "opus": {
        "provider": "anthropic",
        "model":    "claude-opus-4-8",
    },
    # --- OpenAI ---
    "gpt-4o-mini": {
        "provider": "openai",
        "model":    "gpt-4o-mini",
    },
    "gpt-4o": {
        "provider": "openai",
        "model":    "gpt-4o",
    },
    "o1": {
        "provider": "openai",
        "model":    "o1",
    },
    # --- Google Gemini ---
    "gemini-flash": {
        "provider": "gemini",
        "model":    "gemini-2.0-flash",
    },
    "gemini-pro": {
        "provider": "gemini",
        "model":    "gemini-2.5-pro",
    },
    # --- DeepSeek (OpenAI-compatible endpoint) ---
    "deepseek-chat": {
        "provider":  "deepseek",
        "model":     "deepseek-chat",
    },
    "deepseek-r1": {
        "provider":  "deepseek",
        "model":     "deepseek-reasoner",  # chain-of-thought reasoning model
    },
    # --- Ollama (local, zero cost) ---
    "llama3": {
        "provider": "ollama",
        "model":    "llama3.3:70b",
    },
    "mistral": {
        "provider": "ollama",
        "model":    "mistral:7b",
    },
}

# Per-agent env var → alias
AGENT_MODEL_ENVS: dict[str, str] = {
    "coordinator": os.getenv("COORDINATOR_MODEL", "haiku"),
    "research":    os.getenv("RESEARCH_MODEL",    "sonnet"),
    "strategy":    os.getenv("STRATEGY_MODEL",    "sonnet"),
    "synthesis":   os.getenv("SYNTHESIS_MODEL",   "sonnet"),
}


@lru_cache(maxsize=16)
def build_chat_model(alias: str) -> BaseChatModel:
    """
    Return a cached BaseChatModel for the given alias.

    LangSmith traces every call automatically when LANGCHAIN_TRACING_V2=true.
    No manual audit log code needed for LangGraph nodes.
    """
    if alias not in MODEL_REGISTRY:
        raise KeyError(f"Unknown model alias {alias!r}. Available: {sorted(MODEL_REGISTRY)}")

    cfg      = MODEL_REGISTRY[alias]
    provider = cfg["provider"]
    model    = cfg["model"]

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(model=model, api_key=os.environ["ANTHROPIC_API_KEY"])

    if provider == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model=model, api_key=os.environ["OPENAI_API_KEY"])

    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ["GOOGLE_API_KEY"]
        return ChatGoogleGenerativeAI(model=model, google_api_key=api_key)

    if provider == "deepseek":
        # DeepSeek exposes an OpenAI-compatible REST API — no separate package needed
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=model,
            api_key=os.environ["DEEPSEEK_API_KEY"],
            base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
        )

    if provider == "ollama":
        from langchain_ollama import ChatOllama
        return ChatOllama(
            model=model,
            base_url=os.getenv("OLLAMA_HOST", "http://localhost:11434"),
        )

    raise ValueError(f"Unsupported provider: {provider!r}")


def get_agent_model(agent_name: str, override: str | None = None) -> BaseChatModel:
    """Resolve and build the model for a named agent."""
    alias = override or AGENT_MODEL_ENVS.get(agent_name, "sonnet")
    return build_chat_model(alias)
```

### Notes on DeepSeek

- **deepseek-chat**: strong general-purpose model, priced aggressively (~$0.07/M input tokens).
  Excellent substitute for Sonnet on ResearchAgent and StrategyAgent — similar quality, much cheaper.
- **deepseek-r1**: reasoning model (chain-of-thought, like o1). Useful for StrategyAgent
  when the position sizing and hedge logic needs more careful multi-step reasoning.
  Use sparingly — slower and more expensive than deepseek-chat.
- Both use the same `DEEPSEEK_API_KEY` and OpenAI-compatible base URL.
  No additional Python package is required beyond `langchain-openai`.

---

## 1.5 — Structured Output Pattern

Every LangGraph node that calls an LLM uses `.with_structured_output()`.
This replaces all `_parse_json()` + regex fallback code from the skeleton.

```python
from pydantic import BaseModel
from app.modules.llm.model_factory import build_chat_model

class ResearchContext(BaseModel):
    dominant_theme: str
    contagion_links: list[dict]
    squeeze_risk_tickers: list[str]
    granger_leads: list[dict]
    regime_note: str

llm = build_chat_model("sonnet")
structured_llm = llm.with_structured_output(ResearchContext)

result: ResearchContext = structured_llm.invoke(messages)
# result is a validated Pydantic object — no JSON parsing, no regex
```

LangSmith records the full prompt, response, token counts, and latency for every `.invoke()`.

---

## 1.6 — LangSmith Project Setup

1. Create account at `smith.langchain.com`
2. Create a project named `marketai-options-analysis`
3. Copy the API key → set `LANGCHAIN_API_KEY` in `.env`
4. Set `LANGCHAIN_TRACING_V2=true`

From that point every LangGraph `.invoke()` appears in the LangSmith UI automatically:
- Full prompt + response for every node
- Token counts + latency per node
- Graph execution path (which edges were taken)
- Error traces with full context
- Cost estimates (LangSmith computes these from token counts)

No additional code is required — tracing is injected at the `BaseChatModel` level.

---

## Phase 1 Deliverables

- [ ] `requirements.txt` — add langgraph, langchain-core, provider packages, langsmith
- [ ] `.env.example` — add all new env vars
- [ ] `llm/model_factory.py` — `build_chat_model()` + `get_agent_model()` + `MODEL_REGISTRY`
- [ ] LangSmith project created, API key in `.env`
- [ ] Smoke test: `build_chat_model("sonnet").invoke([{"role":"user","content":"ping"}])`
- [ ] Confirm DeepSeek endpoint reachable: `build_chat_model("deepseek-chat").invoke(...)`

## Commit checkpoint

```
feat(agents/phase1): model factory, LangSmith wiring, DeepSeek support
```
