"""
Conviction Scorer — real-time composite score for a single unusual volume event.

Formula (geometric mean with exponent weights):
    conviction = quality^0.5 × direction^0.3 × magnitude_capped^0.2 × regime_multiplier

Where:
    quality          = P(signal is informed)  — from SignalQualityModel
    direction        = P(underlying moves in option's direction) — from DirectionModel[C/P]
    magnitude_capped = min(prob_exceeds_2pct, 1.0) from MagnitudeModel
    regime_multiplier = 0.7 – 1.3 from RegimeModel

The scorer is stateful: models are loaded once and reused.
Thread safety: each FastAPI worker loads its own scorer (no shared state).
"""
import logging
import os
from dataclasses import dataclass, field
from functools import cached_property

import numpy as np

from app.modules.tos.ml.features.tos_feature_builder import (
    ALL_FEATURES,
    DIRECTION_FEATURES,
    REGIME_FEATURES,
    build_event_features,
)
from app.modules.tos.ml.models.direction_model import DirectionModel
from app.modules.tos.ml.models.magnitude_model import MagnitudeModel
from app.modules.tos.ml.models.regime_model import RegimeModel
from app.modules.tos.ml.models.signal_quality_model import SignalQualityModel

log = logging.getLogger(__name__)

ARTIFACTS_PATH = os.getenv("MODEL_ARTIFACTS_PATH", "/app/artifacts")


@dataclass
class ConvictionResult:
    signal_id: str
    symbol: str
    option_type: str
    quality_score: float
    direction_score: float
    magnitude_score: float
    regime_name: str
    regime_multiplier: float
    conviction_score: float
    # optional enrichment
    shap_features: dict = field(default_factory=dict)
    sequence_quality: float | None = None
    cluster_quality: float | None = None

    def to_dict(self) -> dict:
        return {
            "signal_id":          self.signal_id,
            "symbol":             self.symbol,
            "option_type":        self.option_type,
            "quality_score":      round(self.quality_score, 4),
            "direction_score":    round(self.direction_score, 4),
            "magnitude_score":    round(self.magnitude_score, 4),
            "regime":             self.regime_name,
            "regime_multiplier":  round(self.regime_multiplier, 3),
            "conviction_score":   round(self.conviction_score, 4),
            "sequence_quality":   self.sequence_quality,
            "cluster_quality":    self.cluster_quality,
        }


class ConvictionScorer:
    """
    Loads all models once, scores events in real time.

    Graceful degradation: if a model artifact is missing, that component
    defaults to 0.5 (neutral) so the other models still contribute.
    """

    def __init__(self):
        self._quality_model: SignalQualityModel | None = None
        self._direction_c: DirectionModel | None = None
        self._direction_p: DirectionModel | None = None
        self._magnitude_model: MagnitudeModel | None = None
        self._regime_model: RegimeModel | None = None
        self._loaded = False

    def load_models(self) -> None:
        for name, loader in [
            ("quality",      lambda: SignalQualityModel.load()),
            ("direction_c",  lambda: DirectionModel.load("C")),
            ("direction_p",  lambda: DirectionModel.load("P")),
            ("magnitude",    lambda: MagnitudeModel.load()),
            ("regime",       lambda: RegimeModel.load()),
        ]:
            try:
                obj = loader()
                setattr(self, f"_{name}_model" if name not in ("direction_c", "direction_p")
                        else f"_{name}", obj)
                log.info("Loaded %s model", name)
            except FileNotFoundError:
                log.warning("Model not found: %s — will use neutral default", name)
        self._loaded = True

    def score(self, signal_id: str, include_shap: bool = False) -> ConvictionResult:
        if not self._loaded:
            self.load_models()

        features = build_event_features(signal_id)
        if features is None:
            raise ValueError(f"signal_id {signal_id} not found in TOS database")

        symbol      = str(features.get("symbol", ""))
        option_type = str(features.get("option_type", "C"))

        # --- Quality score ---
        quality_score = 0.5
        shap_features: dict = {}
        if self._quality_model is not None:
            X_q = self._to_array(features, ALL_FEATURES)
            quality_score = float(self._quality_model.predict_proba(X_q)[0])
            if include_shap:
                shap_features = self._quality_model.explain(X_q)

        # --- Direction score ---
        direction_score = 0.5
        direction_model = self._direction_c if option_type == "C" else self._direction_p
        if direction_model is not None:
            X_d = self._to_array(features, DIRECTION_FEATURES)
            direction_score = float(direction_model.predict_proba(X_d)[0])

        # --- Magnitude score ---
        magnitude_score = 0.5
        if self._magnitude_model is not None:
            X_m = self._to_array(features, ALL_FEATURES)
            magnitude_score = float(np.clip(
                self._magnitude_model.prob_exceeds(X_m, threshold=0.02)[0], 0, 1
            ))

        # --- Regime ---
        regime_name       = "choppy_range"
        regime_multiplier = 1.0
        if self._regime_model is not None:
            regime_feat = {k: features.get(k, 0.0) for k in REGIME_FEATURES}
            regime_name       = self._regime_model.predict_regime(regime_feat)
            regime_multiplier = self._regime_model.get_multiplier(regime_name)

        # --- Composite conviction ---
        conviction = _geometric_conviction(
            quality_score, direction_score, magnitude_score, regime_multiplier
        )

        return ConvictionResult(
            signal_id=signal_id,
            symbol=symbol,
            option_type=option_type,
            quality_score=quality_score,
            direction_score=direction_score,
            magnitude_score=magnitude_score,
            regime_name=regime_name,
            regime_multiplier=regime_multiplier,
            conviction_score=conviction,
            shap_features=shap_features,
        )

    def score_batch(
        self,
        signal_ids: list[str],
        include_shap: bool = False,
    ) -> list[ConvictionResult]:
        return [self.score(sid, include_shap=include_shap) for sid in signal_ids]

    @staticmethod
    def _to_array(features: dict, col_list: list[str]) -> np.ndarray:
        return np.array([[features.get(c, 0.0) for c in col_list]], dtype=np.float64)


def _geometric_conviction(
    quality: float,
    direction: float,
    magnitude: float,
    regime_mult: float,
    eps: float = 1e-6,
) -> float:
    """
    Weighted geometric mean then scaled by regime multiplier.
    All inputs clamped to [eps, 1-eps] to avoid log(0).
    """
    q = float(np.clip(quality,   eps, 1 - eps))
    d = float(np.clip(direction, eps, 1 - eps))
    m = float(np.clip(magnitude, eps, 1 - eps))
    geo = q ** 0.5 * d ** 0.3 * m ** 0.2
    return float(np.clip(geo * regime_mult, 0, 1))


# Module-level singleton (loaded lazily on first request)
_scorer: ConvictionScorer | None = None


def get_scorer() -> ConvictionScorer:
    global _scorer
    if _scorer is None:
        _scorer = ConvictionScorer()
        _scorer.load_models()
    return _scorer
