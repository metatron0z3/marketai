"""
TOS Score API — real-time conviction scoring endpoints.
"""
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.modules.tos.ml.inference.conviction_scorer import get_scorer
from app.modules.tos.ml.research.gamma_squeeze_detect import analyze_symbol

log = logging.getLogger(__name__)
router = APIRouter()


class ScoreRequest(BaseModel):
    signal_ids: list[str]
    include_shap: bool = False


@router.get("/score/{signal_id}")
def score_signal(
    signal_id: str,
    include_shap: bool = Query(False),
):
    """
    Score a single unusual volume event in real time.
    Returns conviction_score and component breakdown.
    """
    try:
        scorer = get_scorer()
        result = scorer.score(signal_id, include_shap=include_shap)
        return result.to_dict()
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        log.exception("Scoring failed for %s", signal_id)
        raise HTTPException(500, f"Scoring error: {e}")


@router.post("/score/batch")
def score_batch(request: ScoreRequest):
    """
    Score multiple signal IDs in a single request.
    Useful for the frontend leaderboard view.
    """
    if len(request.signal_ids) > 100:
        raise HTTPException(400, "Max 100 signal IDs per batch request")
    try:
        scorer = get_scorer()
        results = scorer.score_batch(request.signal_ids, include_shap=request.include_shap)
        return [r.to_dict() for r in results]
    except Exception as e:
        log.exception("Batch scoring failed")
        raise HTTPException(500, f"Batch scoring error: {e}")


@router.get("/score/leaderboard")
def get_leaderboard(
    symbol: Optional[str] = Query(None),
    min_conviction: float  = Query(0.6, ge=0, le=1),
    limit: int             = Query(20,  ge=1, le=100),
):
    """Top signals by conviction score (from pre-computed conviction_scores table)."""
    from app.modules.tos.db.tos_db import get_tos_postgres, tos_available
    if not tos_available():
        raise HTTPException(503, "TOS database unavailable")

    conn = get_tos_postgres()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT cs.signal_id, cs.symbol, cs.option_type,
                       cs.conviction_score, cs.quality_score,
                       cs.direction_score, cs.magnitude_score,
                       cs.regime, cs.scored_at,
                       sc.strike, sc.days_to_expiry,
                       sc.premium_total, sc.volume_ratio_20d,
                       sc.detected_at
                FROM   conviction_scores cs
                JOIN   signal_catalog sc ON cs.signal_id = sc.signal_id
                WHERE (%(symbol)s IS NULL OR cs.symbol = %(symbol)s)
                  AND  cs.conviction_score >= %(min_conviction)s
                ORDER  BY cs.conviction_score DESC
                LIMIT  %(limit)s
            """, {"symbol": symbol, "min_conviction": min_conviction, "limit": limit})
            rows = cur.fetchall()
            cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in rows]
    finally:
        conn.close()


@router.get("/score/regime")
def get_current_regime():
    """
    Predict the current market regime from latest SPY/VIX context.
    Returns regime name and multiplier used in conviction scoring.
    """
    try:
        from app.modules.tos.ml.models.regime_model import RegimeModel
        model = RegimeModel.load()

        # Pull latest market context from TOS QuestDB
        from app.modules.tos.db.tos_db import get_tos_questdb, tos_available
        if not tos_available():
            return {"regime": "unknown", "multiplier": 1.0, "source": "unavailable"}

        conn = get_tos_questdb()
        with conn.cursor() as cur:
            cur.execute("""
                SELECT atm_iv, iv_rank
                FROM   iv_surface_snapshots
                WHERE  symbol = 'SPY'
                ORDER  BY snapshot_time DESC
                LIMIT  1
            """)
            spy_row = cur.fetchone()
        conn.close()

        feat = RegimeModel.build_regime_features(
            vix_level=spy_row[0] * 100 if spy_row else 20,
            vix_1w_change=0,
            vix_percentile_60d=spy_row[1] if spy_row else 50,
            spy_return_5d=0, spy_return_20d=0, spy_rsi_14=50,
            spy_vol_ratio_20d=1.0, watchlist_avg_iv_rank=50,
            watchlist_avg_skew=0, spy_term_slope=0,
        )
        regime = model.predict_regime(feat)
        multiplier = model.get_multiplier(regime)
        return {"regime": regime, "multiplier": multiplier, "source": "model"}

    except FileNotFoundError:
        return {"regime": "unknown", "multiplier": 1.0, "source": "no_model"}
    except Exception as e:
        log.exception("Regime detection failed")
        raise HTTPException(500, str(e))


@router.get("/score/squeeze/{symbol}")
def get_squeeze_score(symbol: str):
    """Gamma squeeze probability score for a ticker."""
    result = analyze_symbol(symbol)
    if result is None:
        raise HTTPException(503, "TOS data unavailable for gamma squeeze analysis")
    return result.to_dict()
