"""
ResearchAgent — one LLM call per run (mid-tier model).

Pre-work (code, no LLM):
  - sector_contagion: cross-ticker lag correlations (1h, 2h, 4h)
  - gamma_squeeze_detect: squeeze probability per flagged ticker
  - granger_causality: which flow features Granger-cause returns (p < 0.05)

LLM role:
  Given the quantitative outputs above, synthesize a ResearchContext:
  dominant theme, contagion links, squeeze risks, Granger leaders, regime note.

Output: ResearchContext dict — consumed by StrategyAgent and SynthesisAgent.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from app.modules.agents.base_agent import AgentContext, BaseAgent
from app.modules.agents.ml_agent import ScoredBatch

log = logging.getLogger(__name__)


class ResearchAgent(BaseAgent):
    name = "research"
    default_model_alias = "sonnet"

    def run(self, ctx: AgentContext, scored_batches: list[ScoredBatch], **_) -> dict:
        flagged = [s for b in scored_batches if b for s in b.flagged]
        if not flagged:
            log.info("ResearchAgent: no flagged signals — skipping")
            return {"research_context": _empty_context()}

        log.info("ResearchAgent: analysing %d flagged signals across %d symbols",
                 len(flagged), len(scored_batches))

        # --- Code pre-work (quantitative, no LLM) ---
        contagion = self._run_contagion([s.symbol for s in flagged])
        squeeze   = self._run_squeeze_detector(flagged)
        granger   = self._run_granger(flagged)
        regime    = self._get_regime(flagged)

        # --- LLM synthesis ---
        prompt_data = {
            "flagged_signals": [
                {
                    "symbol":           s.symbol,
                    "option_type":      s.option_type,
                    "conviction_score": round(s.conviction_score, 3),
                    "regime":           s.regime_name,
                    "shap_top3":        s.shap_top3,
                }
                for s in flagged[:10]   # cap context size
            ],
            "contagion_map": contagion,
            "squeeze_scores": squeeze,
            "granger_leads": granger,
            "regime_summary": regime,
        }

        system = (
            "You are a quantitative options analyst. "
            "You receive structured JSON from ML models and return ONLY valid JSON."
        )
        user = (
            "Given the following ML pipeline outputs, synthesise a ResearchContext.\n\n"
            f"```json\n{json.dumps(prompt_data, indent=2)}\n```\n\n"
            "Return ONLY this JSON structure (no markdown, no explanation):\n"
            "{\n"
            '  "dominant_theme": "<string>",\n'
            '  "contagion_links": [{"source":"","target":"","lag_hours":0,"confidence":0.0}],\n'
            '  "squeeze_risk_tickers": [""],\n'
            '  "granger_leads": [{"feature":"","target_return":"5d","p_value":0.0}],\n'
            '  "regime_note": "<string>"\n'
            "}"
        )

        try:
            raw = self._llm(
                messages=[{"role": "user", "content": user}],
                system=system,
                max_tokens=600,
            )
            ctx_dict = self._parse_json(raw)
        except Exception as exc:
            log.warning("ResearchAgent LLM call failed: %s", exc)
            ctx_dict = _empty_context()

        log.info("ResearchAgent: theme=%r squeeze=%s",
                 ctx_dict.get("dominant_theme"), ctx_dict.get("squeeze_risk_tickers"))
        return {"research_context": ctx_dict}

    # ------------------------------------------------------------------
    # Code pre-work (wrappers around existing research modules)
    # ------------------------------------------------------------------

    def _run_contagion(self, symbols: list[str]) -> list[dict]:
        try:
            from app.modules.tos.ml.research.sector_contagion import compute_contagion_matrix
            matrix = compute_contagion_matrix(symbols, lag_hours=[1, 2, 4])
            return matrix.get("significant_links", [])
        except Exception as exc:
            log.warning("Contagion analysis failed: %s", exc)
            return []

    def _run_squeeze_detector(self, flagged) -> dict[str, float]:
        from app.modules.tos.ml.research.gamma_squeeze_detect import compute_squeeze_score
        result = {}
        for sig in flagged:
            try:
                score = compute_squeeze_score(sig.symbol)
                result[sig.symbol] = round(score, 3)
            except Exception as exc:
                log.warning("Squeeze detection failed for %s: %s", sig.symbol, exc)
        return result

    def _run_granger(self, flagged) -> list[dict]:
        try:
            from app.modules.tos.ml.research.granger_causality import run_granger_tests
            symbols = list({s.symbol for s in flagged})
            return run_granger_tests(symbols, max_lag=5)
        except Exception as exc:
            log.warning("Granger causality failed: %s", exc)
            return []

    def _get_regime(self, flagged) -> str:
        if not flagged:
            return "unknown"
        regime_names = [s.regime_name for s in flagged if s.regime_name]
        if not regime_names:
            return "unknown"
        from collections import Counter
        return Counter(regime_names).most_common(1)[0][0]


def _empty_context() -> dict:
    return {
        "dominant_theme": "insufficient data",
        "contagion_links": [],
        "squeeze_risk_tickers": [],
        "granger_leads": [],
        "regime_note": "no flagged signals",
    }
