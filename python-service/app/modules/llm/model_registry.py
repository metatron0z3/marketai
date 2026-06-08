"""
Model registry — maps human-readable aliases to (provider, model_id) pairs.

Agents reference aliases, not raw model IDs. To switch providers globally,
set env vars: RESEARCH_MODEL=gpt-4o STRATEGY_MODEL=gpt-4o etc.

To add a new model: add an entry to MODEL_REGISTRY. No other changes needed.
"""
from __future__ import annotations

import os

from app.modules.llm.backends import LLMBackend, LLMResponse, get_backend_for_provider

MODEL_REGISTRY: dict[str, tuple[str, str]] = {
    # alias            provider       model_id
    # --- fast / cheap tier ---
    "haiku":           ("anthropic", "claude-haiku-4-5-20251001"),
    "gpt-4o-mini":     ("openai",   "gpt-4o-mini"),
    "gemini-flash":    ("gemini",   "gemini-2.0-flash"),
    "llama3":          ("ollama",   "llama3.3:70b"),
    # --- mid tier ---
    "sonnet":          ("anthropic", "claude-sonnet-4-6"),
    "gpt-4o":          ("openai",   "gpt-4o"),
    "gemini-pro":      ("gemini",   "gemini-2.5-pro"),
    # --- full / heavy tier ---
    "opus":            ("anthropic", "claude-opus-4-8"),
    "o1":              ("openai",   "o1"),
}

# Per-agent env var overrides (set in docker-compose or .env)
AGENT_MODEL_ENV: dict[str, str] = {
    "coordinator": "COORDINATOR_MODEL",
    "data":        "DATA_MODEL",         # unused (code-only), kept for future
    "ml":          "ML_MODEL",           # unused (code-only), kept for future
    "research":    "RESEARCH_MODEL",
    "strategy":    "STRATEGY_MODEL",
    "synthesis":   "SYNTHESIS_MODEL",
}

# Defaults if env var not set
AGENT_MODEL_DEFAULTS: dict[str, str] = {
    "coordinator": "haiku",
    "data":        "haiku",
    "ml":          "haiku",
    "research":    "sonnet",
    "strategy":    "sonnet",
    "synthesis":   "sonnet",
}


def resolve_alias(alias: str) -> tuple[str, str]:
    """Return (provider, model_id) for a registry alias."""
    if alias not in MODEL_REGISTRY:
        raise KeyError(
            f"Unknown model alias {alias!r}. "
            f"Available: {sorted(MODEL_REGISTRY)}"
        )
    return MODEL_REGISTRY[alias]


def get_backend(alias: str) -> tuple[LLMBackend, str]:
    """Return (backend_instance, model_id) ready for a .complete() call."""
    provider, model_id = resolve_alias(alias)
    backend = get_backend_for_provider(provider)
    return backend, model_id


def resolve_agent_alias(agent_name: str, override: str | None = None) -> str:
    """
    Resolve the model alias for a named agent.

    Priority:
      1. explicit override argument
      2. environment variable (e.g. RESEARCH_MODEL=gpt-4o)
      3. built-in default for that agent
    """
    if override:
        return override
    env_key = AGENT_MODEL_ENV.get(agent_name)
    if env_key:
        env_val = os.getenv(env_key)
        if env_val:
            return env_val
    return AGENT_MODEL_DEFAULTS.get(agent_name, "sonnet")
