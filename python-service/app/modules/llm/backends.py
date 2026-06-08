"""
LLM Backend abstraction — model-agnostic interface for all agent LLM calls.

Usage:
    from app.modules.llm.backends import get_backend

    backend, model_id = get_backend("sonnet")
    resp = backend.complete(messages=[...], model=model_id, max_tokens=500)
    print(resp.text, resp.input_tokens, resp.provider)

Add a new provider by implementing LLMBackend Protocol and registering
the alias in model_registry.py — no changes needed anywhere else.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass
class LLMResponse:
    text: str
    input_tokens: int
    output_tokens: int
    model: str
    provider: str
    latency_ms: int = 0


@runtime_checkable
class LLMBackend(Protocol):
    provider: str

    def complete(
        self,
        messages: list[dict],
        model: str,
        max_tokens: int,
        temperature: float = 0.0,
        system: str | None = None,
    ) -> LLMResponse: ...


# ---------------------------------------------------------------------------
# Anthropic backend (default — maps to existing behavior)
# ---------------------------------------------------------------------------

class AnthropicBackend:
    provider = "anthropic"

    def __init__(self) -> None:
        self._client = None

    def _get_client(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        return self._client

    def complete(
        self,
        messages: list[dict],
        model: str,
        max_tokens: int,
        temperature: float = 0.0,
        system: str | None = None,
    ) -> LLMResponse:
        kwargs: dict = dict(model=model, max_tokens=max_tokens, messages=messages)
        if system:
            kwargs["system"] = system
        if temperature != 0.0:
            kwargs["temperature"] = temperature

        t0 = time.monotonic()
        raw = self._get_client().messages.create(**kwargs)
        latency_ms = int((time.monotonic() - t0) * 1000)

        return LLMResponse(
            text=raw.content[0].text,
            input_tokens=raw.usage.input_tokens,
            output_tokens=raw.usage.output_tokens,
            model=model,
            provider=self.provider,
            latency_ms=latency_ms,
        )


# ---------------------------------------------------------------------------
# OpenAI backend
# ---------------------------------------------------------------------------

class OpenAIBackend:
    provider = "openai"

    def __init__(self) -> None:
        self._client = None

    def _get_client(self):
        if self._client is None:
            import openai
            self._client = openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        return self._client

    def complete(
        self,
        messages: list[dict],
        model: str,
        max_tokens: int,
        temperature: float = 0.0,
        system: str | None = None,
    ) -> LLMResponse:
        msgs = messages[:]
        if system:
            msgs = [{"role": "system", "content": system}] + msgs

        t0 = time.monotonic()
        raw = self._get_client().chat.completions.create(
            model=model,
            messages=msgs,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        latency_ms = int((time.monotonic() - t0) * 1000)

        return LLMResponse(
            text=raw.choices[0].message.content or "",
            input_tokens=raw.usage.prompt_tokens,
            output_tokens=raw.usage.completion_tokens,
            model=model,
            provider=self.provider,
            latency_ms=latency_ms,
        )


# ---------------------------------------------------------------------------
# Google Gemini backend
# ---------------------------------------------------------------------------

class GeminiBackend:
    provider = "gemini"

    def __init__(self) -> None:
        self._configured = False

    def _ensure_configured(self) -> None:
        if not self._configured:
            import google.generativeai as genai
            genai.configure(
                api_key=os.environ.get("GEMINI_API_KEY") or os.environ["GOOGLE_API_KEY"]
            )
            self._configured = True

    def complete(
        self,
        messages: list[dict],
        model: str,
        max_tokens: int,
        temperature: float = 0.0,
        system: str | None = None,
    ) -> LLMResponse:
        import google.generativeai as genai

        self._ensure_configured()

        config = genai.GenerationConfig(
            max_output_tokens=max_tokens,
            temperature=temperature,
        )
        gemini_model = genai.GenerativeModel(
            model_name=model,
            generation_config=config,
            system_instruction=system,
        )

        # Convert OpenAI-style messages to Gemini Contents
        history = []
        last_user = None
        for m in messages:
            role = "user" if m["role"] == "user" else "model"
            if m["role"] == "user":
                last_user = m["content"]
            history.append({"role": role, "parts": [m["content"]]})

        t0 = time.monotonic()
        resp = gemini_model.generate_content(history)
        latency_ms = int((time.monotonic() - t0) * 1000)

        usage = resp.usage_metadata
        return LLMResponse(
            text=resp.text,
            input_tokens=getattr(usage, "prompt_token_count", 0),
            output_tokens=getattr(usage, "candidates_token_count", 0),
            model=model,
            provider=self.provider,
            latency_ms=latency_ms,
        )


# ---------------------------------------------------------------------------
# Ollama backend (local, zero cost)
# ---------------------------------------------------------------------------

class OllamaBackend:
    provider = "ollama"

    def __init__(self) -> None:
        self._host = os.getenv("OLLAMA_HOST", "http://localhost:11434")

    def complete(
        self,
        messages: list[dict],
        model: str,
        max_tokens: int,
        temperature: float = 0.0,
        system: str | None = None,
    ) -> LLMResponse:
        import requests

        msgs = messages[:]
        if system:
            msgs = [{"role": "system", "content": system}] + msgs

        t0 = time.monotonic()
        resp = requests.post(
            f"{self._host}/api/chat",
            json={
                "model": model,
                "messages": msgs,
                "stream": False,
                "options": {"num_predict": max_tokens, "temperature": temperature},
            },
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()
        latency_ms = int((time.monotonic() - t0) * 1000)

        prompt_eval = data.get("prompt_eval_count", 0)
        eval_count  = data.get("eval_count", 0)

        return LLMResponse(
            text=data["message"]["content"],
            input_tokens=prompt_eval,
            output_tokens=eval_count,
            model=model,
            provider=self.provider,
            latency_ms=latency_ms,
        )


# ---------------------------------------------------------------------------
# Factory — used by model_registry.get_backend()
# ---------------------------------------------------------------------------

_PROVIDER_MAP: dict[str, type] = {
    "anthropic": AnthropicBackend,
    "openai":    OpenAIBackend,
    "gemini":    GeminiBackend,
    "ollama":    OllamaBackend,
}

_instances: dict[str, LLMBackend] = {}


def get_backend_for_provider(provider: str) -> LLMBackend:
    if provider not in _instances:
        cls = _PROVIDER_MAP.get(provider)
        if cls is None:
            raise ValueError(f"Unknown LLM provider: {provider!r}. "
                             f"Supported: {list(_PROVIDER_MAP)}")
        _instances[provider] = cls()
    return _instances[provider]
