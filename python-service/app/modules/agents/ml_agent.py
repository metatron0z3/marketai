"""
MLAgent — code-only agent (no LLM calls).

Runs the existing ConvictionScorer stack on a SignalBatch from DataAgent:
  quality × direction × magnitude × regime → conviction_score

Also computes SHAP top-3 features for signals above the flag threshold,
and looks up the 30-day cluster hit rate from historical signal_catalog data.

Output: ScoredBatch — the input to ResearchAgent and StrategyAgent.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.modules.agents.base_agent import AgentContext, BaseAgent
from app.modules.agents.data_agent import SignalBatch

log = logging.getLogger(__name__)

CONVICTION_THRESHOLD = 0.65
CLUSTER_HIT_RATE_THRESHOLD = 0.50


@dataclass
class ScoredSignal:
    signal_id: str
    symbol: str
    option_type: str
    conviction_score: float
    quality_score: float
    direction_score: float
    magnitude_score: float
    regime_name: str
    regime_multiplier: float
    shap_top3: list[dict]    # [{"feature": str, "value": float}, ...]
    cluster_hit_rate: float
    raw_score: float         # DataAgent ranking score
    features: dict           # full feature vector


@dataclass
class ScoredBatch:
    scored: list[ScoredSignal]
    flagged: list[ScoredSignal]   # conviction > threshold AND cluster_hit_rate > threshold
    symbol: str
    date: str


class MLAgent(BaseAgent):
    name = "ml"
    default_model_alias = "haiku"   # unused — no LLM calls

    def run(self, ctx: AgentContext, batch: SignalBatch, **_) -> dict:
        if batch is None or not batch.signals:
            return {"symbol": batch.symbol if batch else "?", "count": 0, "scored_batch": None}

        log.info("MLAgent: scoring %d signals for %s", len(batch.signals), batch.symbol)

        from app.modules.tos.ml.inference.conviction_scorer import get_scorer
        scorer = get_scorer()

        scored: list[ScoredSignal] = []
        for sig in batch.signals:
            sid = str(sig.get("id", ""))
            try:
                result = scorer.score(sid, include_shap=True)
                cluster_hr = self._cluster_hit_rate(sig, batch)
                scored.append(ScoredSignal(
                    signal_id=sid,
                    symbol=result.symbol,
                    option_type=result.option_type,
                    conviction_score=result.conviction_score,
                    quality_score=result.quality_score,
                    direction_score=result.direction_score,
                    magnitude_score=result.magnitude_score,
                    regime_name=result.regime_name,
                    regime_multiplier=result.regime_multiplier,
                    shap_top3=self._top_shap(result.shap_features),
                    cluster_hit_rate=cluster_hr,
                    raw_score=float(sig.get("_raw_score", 0)),
                    features=sig,
                ))
            except Exception as exc:
                log.warning("MLAgent scoring failed for %s: %s", sid, exc)

        scored.sort(key=lambda s: s.conviction_score, reverse=True)
        flagged = [
            s for s in scored
            if s.conviction_score >= CONVICTION_THRESHOLD
            and s.cluster_hit_rate >= CLUSTER_HIT_RATE_THRESHOLD
        ]

        log.info(
            "MLAgent: %d scored, %d flagged for %s",
            len(scored), len(flagged), batch.symbol
        )
        sb = ScoredBatch(scored=scored, flagged=flagged, symbol=batch.symbol, date=batch.date)
        return {"symbol": batch.symbol, "count": len(scored), "flagged": len(flagged), "scored_batch": sb}

    # ------------------------------------------------------------------

    @staticmethod
    def _top_shap(shap_dict: dict, n: int = 3) -> list[dict]:
        if not shap_dict:
            return []
        sorted_feats = sorted(shap_dict.items(), key=lambda kv: abs(kv[1]), reverse=True)
        return [{"feature": k, "value": round(v, 4)} for k, v in sorted_feats[:n]]

    @staticmethod
    def _cluster_hit_rate(sig: dict, batch: SignalBatch) -> float:
        """
        Stub: return historical hit rate from signal_catalog for signals in the
        same dte_bucket + otm_pct cluster. 0.5 (neutral) when no history available.
        """
        # TODO: query signal_catalog for past 30-day hit rates per cluster archetype.
        # For now return ticker_signal_hit_rate_30d from the feature vector if present.
        return float(sig.get("ticker_signal_hit_rate_30d", 0.5))
