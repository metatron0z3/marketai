"""
Multi-provider pricing constants and per-call cost computation.

Prices as of 2026-06 (USD per million tokens).
Update MODEL_PRICING when providers publish new rates.
"""
from dataclasses import dataclass

MODEL_PRICING: dict[str, dict[str, float]] = {
    # ── Anthropic Claude 4 ─────────────────────────────────────────────
    "claude-opus-4-8":            {"input": 15.00,  "output": 75.00},
    "claude-sonnet-4-6":          {"input":  3.00,  "output": 15.00},
    "claude-haiku-4-5":           {"input":  0.80,  "output":  4.00},
    "claude-haiku-4-5-20251001":  {"input":  0.80,  "output":  4.00},
    # ── Anthropic Claude 3 (legacy) ────────────────────────────────────
    "claude-3-5-sonnet-20241022": {"input":  3.00,  "output": 15.00},
    "claude-3-haiku-20240307":    {"input":  0.25,  "output":  1.25},
    # ── OpenAI ────────────────────────────────────────────────────────
    "gpt-4o":                     {"input":  2.50,  "output": 10.00},
    "gpt-4o-mini":                {"input":  0.15,  "output":  0.60},
    "o1":                         {"input": 15.00,  "output": 60.00},
    # ── Google Gemini ─────────────────────────────────────────────────
    "gemini-2.0-flash":           {"input":  0.075, "output":  0.30},
    "gemini-2.5-pro":             {"input":  1.25,  "output": 10.00},
    # ── DeepSeek ─────────────────────────────────────────────────────
    "deepseek-chat":              {"input":  0.07,  "output":  0.28},
    "deepseek-reasoner":          {"input":  0.55,  "output":  2.19},
    # ── Ollama (local, zero cost) ─────────────────────────────────────
    "llama3.3:70b":               {"input":  0.0,   "output":  0.0},
    "mistral:7b":                 {"input":  0.0,   "output":  0.0},
}

MONTHLY_BUDGET_USD = float(50.0)
DAILY_BUDGET_USD   = float(MONTHLY_BUDGET_USD / 22)   # ~22 trading days


@dataclass
class CallCost:
    model: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


def compute_cost(model: str, prompt_tokens: int, completion_tokens: int) -> CallCost:
    pricing = MODEL_PRICING.get(model, MODEL_PRICING["claude-haiku-4-5"])
    cost = (prompt_tokens * pricing["input"] + completion_tokens * pricing["output"]) / 1_000_000
    return CallCost(
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cost_usd=round(cost, 8),
    )
