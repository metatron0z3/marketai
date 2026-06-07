"""
Anthropic pricing constants and per-call cost computation.

Prices as of 2026-06 (USD per million tokens).
Update MODEL_PRICING when Anthropic publishes new rates.
"""
from dataclasses import dataclass

MODEL_PRICING: dict[str, dict[str, float]] = {
    # Claude 4 family
    "claude-opus-4-8":         {"input": 15.00,  "output": 75.00},
    "claude-sonnet-4-6":       {"input":  3.00,  "output": 15.00},
    "claude-haiku-4-5":        {"input":  0.80,  "output":  4.00},
    "claude-haiku-4-5-20251001": {"input": 0.80, "output":  4.00},
    # Claude 3 family (legacy)
    "claude-3-5-sonnet-20241022": {"input": 3.00, "output": 15.00},
    "claude-3-haiku-20240307":    {"input": 0.25, "output":  1.25},
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
