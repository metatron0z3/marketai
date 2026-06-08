"""
StrategyAgent — 1 LLM call per flagged signal (mid-tier model).

Translates a scored signal + research context into concrete trade parameters:
entry condition, strike preference, DTE target, position sizing (Kelly fraction),
stop-loss, profit target, and hedges.

Output per signal: TradeParams dict written to agent_trade_params table.
"""
from __future__ import annotations

import json
import logging
import math

from app.modules.agents.base_agent import AgentContext, BaseAgent
from app.modules.agents.ml_agent import ScoredSignal

log = logging.getLogger(__name__)

# Risk config — override via env if needed
MAX_POSITION_PCT = float(__import__("os").getenv("MAX_POSITION_PCT", "0.03"))   # 3%
STOP_LOSS_PCT    = float(__import__("os").getenv("STOP_LOSS_PCT",    "0.50"))   # 50% of premium
PROFIT_TARGET_PCT = float(__import__("os").getenv("PROFIT_TARGET_PCT", "1.00")) # 100% gain


class StrategyAgent(BaseAgent):
    name = "strategy"
    default_model_alias = "sonnet"

    def run(
        self,
        ctx: AgentContext,
        signal: ScoredSignal,
        research_context: dict,
        **_,
    ) -> dict:
        log.info(
            "StrategyAgent: building trade params for %s %s (conviction=%.3f)",
            signal.symbol, signal.option_type, signal.conviction_score
        )

        kelly = self._kelly_fraction(signal)
        position_pct = min(kelly / 2, MAX_POSITION_PCT)   # half-Kelly, capped at max

        system = (
            "You are a professional options trader and risk manager. "
            "Return ONLY valid JSON with no markdown or explanation."
        )

        user = (
            f"Signal details:\n"
            f"  Ticker: {signal.symbol}  Direction: {'CALL' if signal.option_type == 'C' else 'PUT'}\n"
            f"  Conviction: {signal.conviction_score:.3f}  "
            f"  Quality: {signal.quality_score:.3f}  "
            f"  Direction: {signal.direction_score:.3f}  "
            f"  Magnitude: {signal.magnitude_score:.3f}\n"
            f"  Regime: {signal.regime_name} (mult={signal.regime_multiplier:.2f})\n"
            f"  SHAP top features: {json.dumps(signal.shap_top3)}\n\n"
            f"Key features:\n"
            f"  IV Rank: {signal.features.get('iv_rank', 'N/A')}\n"
            f"  DTE bucket: {signal.features.get('dte_bucket', 'N/A')} "
            f"  (0=weekly 1=biweekly 2=monthly 3=quarterly)\n"
            f"  OTM%: {signal.features.get('otm_pct', 'N/A')}\n"
            f"  Premium: ${signal.features.get('premium_total', 0):,.0f}\n\n"
            f"Research context:\n{json.dumps(research_context, indent=2)}\n\n"
            f"Risk config:\n"
            f"  Kelly fraction: {kelly:.3f}  Recommended position: {position_pct*100:.1f}%\n"
            f"  Stop-loss: {STOP_LOSS_PCT*100:.0f}% premium loss\n"
            f"  Profit target: {PROFIT_TARGET_PCT*100:.0f}% gain or close T-3 before expiry\n\n"
            "Produce a TradeParams JSON object with these exact keys:\n"
            "{\n"
            '  "ticker": "",\n'
            '  "direction": "CALL|PUT",\n'
            '  "entry_condition": "",\n'
            '  "strike_preference": "",\n'
            '  "dte_target": "",\n'
            '  "position_sizing": {"kelly_fraction": 0.0, "recommended_pct": "", "max_contracts": 0},\n'
            '  "stop_loss": "",\n'
            '  "profit_target": "",\n'
            '  "hedges": "",\n'
            '  "rationale": ""\n'
            "}"
        )

        try:
            raw = self._llm(
                messages=[{"role": "user", "content": user}],
                system=system,
                max_tokens=700,
                symbol=signal.symbol,
            )
            params = self._parse_json(raw)
        except Exception as exc:
            log.warning("StrategyAgent LLM failed for %s: %s", signal.symbol, exc)
            params = self._fallback_params(signal, kelly, position_pct)

        params["signal_id"]        = signal.signal_id
        params["conviction_score"] = signal.conviction_score

        self._persist(signal.signal_id, signal.symbol, signal.option_type,
                      signal.conviction_score, params)

        return {"signal_id": signal.signal_id, "trade_params": params}

    # ------------------------------------------------------------------

    @staticmethod
    def _kelly_fraction(signal: ScoredSignal) -> float:
        """
        Simplified Kelly: f = (p*(b+1) - 1) / b
          p = direction_score (P win)
          b = magnitude_score * 2 (simplified reward ratio proxy)
        """
        p = signal.direction_score
        b = max(signal.magnitude_score * 2.0, 0.01)
        kelly = (p * (b + 1) - 1) / b
        return max(0.0, min(kelly, 0.5))   # clamp 0–50%

    @staticmethod
    def _fallback_params(signal: ScoredSignal, kelly: float, pos_pct: float) -> dict:
        direction = "CALL" if signal.option_type == "C" else "PUT"
        return {
            "ticker":    signal.symbol,
            "direction": direction,
            "entry_condition": "Market open confirmation",
            "strike_preference": "ATM to 5% OTM",
            "dte_target": "10–21 days",
            "position_sizing": {
                "kelly_fraction":  round(kelly, 3),
                "recommended_pct": f"{pos_pct*100:.1f}%",
                "max_contracts":   5,
            },
            "stop_loss":     f"{STOP_LOSS_PCT*100:.0f}% premium loss",
            "profit_target": f"{PROFIT_TARGET_PCT*100:.0f}% gain",
            "hedges":        "None",
            "rationale":     "LLM call failed — fallback parameters applied",
        }

    def _persist(
        self, signal_id: str, symbol: str, direction: str,
        conviction: float, params: dict
    ) -> None:
        import json as _json
        import os
        from datetime import datetime, timezone

        try:
            from questdb.ingress import Sender, TimestampNanos
            from app.modules.llm.model_registry import resolve_alias

            provider, model_id = resolve_alias(self.model_alias)
            conf = os.getenv("QDB_CLIENT_CONF", "http::addr=questdb:9000;")
            with Sender.from_conf(conf) as sender:
                sender.row(
                    "agent_trade_params",
                    symbols={
                        "symbol":    symbol,
                        "direction": direction,
                        "provider":  provider,
                        "model_id":  model_id,
                    },
                    columns={
                        "signal_id":        signal_id,
                        "conviction_score": conviction,
                        "params_json":      _json.dumps(params),
                    },
                    at=TimestampNanos.now(),
                )
                sender.flush()
        except Exception as exc:
            log.warning("agent_trade_params write failed: %s", exc)
