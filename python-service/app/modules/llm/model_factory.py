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
from __future__ import annotations

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
    # --- DeepSeek (OpenAI-compatible endpoint — no extra package needed) ---
    "deepseek-chat": {
        "provider": "deepseek",
        "model":    "deepseek-chat",
    },
    "deepseek-r1": {
        "provider": "deepseek",
        "model":    "deepseek-reasoner",
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

# Per-agent env var → default alias
AGENT_MODEL_ENVS: dict[str, str] = {
    "coordinator":   os.getenv("COORDINATOR_MODEL",   "haiku"),
    "research":      os.getenv("RESEARCH_MODEL",      "sonnet"),
    "strategy":      os.getenv("STRATEGY_MODEL",      "sonnet"),
    "synthesis":     os.getenv("SYNTHESIS_MODEL",     "sonnet"),
    "archive":       os.getenv("ARCHIVE_MODEL",       "sonnet"),
    "archive_deep":  os.getenv("ARCHIVE_DEEP_MODEL",  "opus"),
    "education":     os.getenv("EDUCATION_MODEL",     "sonnet"),
}


@lru_cache(maxsize=16)
def build_chat_model(alias: str) -> BaseChatModel:
    """
    Return a cached BaseChatModel for the given alias.

    LangSmith traces every call automatically when LANGCHAIN_TRACING_V2=true.
    """
    if alias not in MODEL_REGISTRY:
        raise KeyError(
            f"Unknown model alias {alias!r}. Available: {sorted(MODEL_REGISTRY)}"
        )

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
    """Resolve and build the model for a named agent role."""
    alias = override or AGENT_MODEL_ENVS.get(agent_name, "sonnet")
    return build_chat_model(alias)
