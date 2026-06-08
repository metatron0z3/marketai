"""ml_node — wraps MLAgent + ConvictionScorer; produces scored and flagged signals."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.modules.agents.graph.state import GraphState

log = logging.getLogger(__name__)


def _batch_dict_to_signal_batch(d: dict):
    """Reconstruct a SignalBatch-like object from a plain dict."""
    import pandas as pd
    from app.modules.agents.data_agent import SignalBatch
    return SignalBatch(
        signals=d["signals"],
        feature_matrix=pd.DataFrame(d["signals"]),
        clusters=d["clusters"],
        ranked_ids=d["ranked_ids"],
        symbol=d["symbol"],
        date=d["date"],
    )


def _scored_signal_to_dict(s) -> dict:
    return {
        "signal_id":       s.signal_id,
        "symbol":          s.symbol,
        "option_type":     s.option_type,
        "conviction_score": s.conviction_score,
        "quality_score":   s.quality_score,
        "direction_score": s.direction_score,
        "magnitude_score": s.magnitude_score,
        "regime_name":     s.regime_name,
        "regime_multiplier": s.regime_multiplier,
        "shap_top3":       s.shap_top3,
        "cluster_hit_rate": s.cluster_hit_rate,
        "raw_score":       s.raw_score,
        "features":        s.features,
    }


def ml_node(state: GraphState) -> dict:
    from app.modules.agents.base_agent import AgentContext
    from app.modules.agents.ml_agent import MLAgent

    ctx = AgentContext(
        run_id="",
        target_date=state["target_date"],
        symbols=state["symbols"],
        budget_remaining_usd=0,
    )

    agent = MLAgent()
    scored_batches: list[dict] = []
    flagged: list[dict] = []
    errors: list[str] = []

    for batch_dict in state.get("signal_batches", []):
        try:
            batch = _batch_dict_to_signal_batch(batch_dict)
            result = agent.run(ctx, batch=batch)
            sb = result.get("scored_batch")
            if sb:
                scored_batches.append({
                    "symbol":  sb.symbol,
                    "date":    sb.date,
                    "scored":  [_scored_signal_to_dict(s) for s in sb.scored],
                    "flagged": [_scored_signal_to_dict(s) for s in sb.flagged],
                })
                flagged.extend(_scored_signal_to_dict(s) for s in sb.flagged)
        except Exception as exc:
            msg = f"ml_node {batch_dict.get('symbol', '?')}: {exc}"
            log.warning(msg)
            errors.append(msg)

    log.info("ml_node: %d batches scored, %d flagged", len(scored_batches), len(flagged))
    return {
        "scored_batches":  scored_batches,
        "flagged_signals": flagged,
        "total_flagged":   len(flagged),
        "errors":          errors,
    }
