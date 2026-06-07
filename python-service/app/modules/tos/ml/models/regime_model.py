"""
Model 4 — Market Regime Classifier.

Question: What market regime are we in right now?

Two-stage approach:
  1. GaussianMixture unsupervised clustering discovers natural regime clusters
     from historical SPY/VIX/IV data.
  2. RandomForest supervised classifier assigns a regime label in real-time
     (trained on the cluster assignments from step 1 as pseudo-labels).

Regimes (discovered, then hand-labeled after fitting):
  0  Trending Bull     — low VIX, positive SPY momentum, IV contracting
  1  Trending Bear     — elevated VIX, negative SPY momentum, put skew high
  2  Choppy / Range    — low absolute vol, mean-reverting, no trend
  3  Vol Expansion     — VIX rising fast, term structure inverting
  4  Post-Shock Recovery — VIX spike then fade, oversold bounce setup

regime_multipliers: how much to scale conviction scores in each regime.
Choppy markets discount all directional signals; vol expansion amplifies them.
"""
import os
import pickle
import warnings

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.mixture import GaussianMixture
from sklearn.preprocessing import StandardScaler

from app.modules.tos.ml.features.tos_feature_builder import REGIME_FEATURES


ARTIFACTS_PATH = os.getenv("MODEL_ARTIFACTS_PATH", "/app/artifacts")

N_REGIMES = 5

REGIME_NAMES = {
    0: "trending_bull",
    1: "trending_bear",
    2: "choppy_range",
    3: "vol_expansion",
    4: "post_shock",
}

REGIME_MULTIPLIERS = {
    "trending_bull":    1.10,
    "trending_bear":    1.10,
    "choppy_range":     0.70,
    "vol_expansion":    1.30,
    "post_shock":       0.90,
}


class RegimeModel:
    """
    Detects the current market regime and returns a conviction multiplier.

    Usage:
        model = RegimeModel.load()
        regime_name = model.predict_regime(feature_dict)
        multiplier  = model.get_multiplier(regime_name)
    """

    def __init__(self, n_regimes: int = N_REGIMES):
        self.n_regimes = n_regimes
        self.scaler = StandardScaler()
        self.gmm: GaussianMixture | None = None
        self.classifier: RandomForestClassifier | None = None
        self.regime_map: dict[int, str] = dict(REGIME_NAMES)  # cluster_id → name

    # ------------------------------------------------------------------
    # Stage 1: unsupervised cluster discovery
    # ------------------------------------------------------------------

    def fit_clusters(self, X: np.ndarray) -> np.ndarray:
        """Fit GMM and return cluster labels for hand-labeling."""
        X_scaled = self.scaler.fit_transform(X)
        self.gmm = GaussianMixture(
            n_components=self.n_regimes,
            covariance_type="full",
            random_state=42,
            max_iter=200,
        )
        self.gmm.fit(X_scaled)
        return self.gmm.predict(X_scaled)

    # ------------------------------------------------------------------
    # Stage 2: supervised assignment
    # ------------------------------------------------------------------

    def fit_classifier(
        self,
        X: np.ndarray,
        pseudo_labels: np.ndarray,
        regime_map: dict[int, str] | None = None,
    ) -> None:
        """
        Train a RandomForest to predict regime from features in real-time.

        pseudo_labels: output of fit_clusters() — cluster IDs
        regime_map:    {cluster_id: regime_name} — supply after hand-labeling
        """
        if regime_map:
            self.regime_map = regime_map
        X_scaled = self.scaler.transform(X)
        self.classifier = RandomForestClassifier(
            n_estimators=200,
            max_depth=6,
            min_samples_leaf=20,
            random_state=42,
            class_weight="balanced",
        )
        self.classifier.fit(X_scaled, pseudo_labels)

    # ------------------------------------------------------------------
    # Inference
    # ------------------------------------------------------------------

    def predict_regime_id(self, X: np.ndarray) -> np.ndarray:
        if self.classifier is None:
            raise RuntimeError("Regime classifier not trained")
        return self.classifier.predict(self.scaler.transform(X))

    def predict_regime(self, feature_dict: dict) -> str:
        """Single-event inference. Returns regime name string."""
        x = np.array([[feature_dict.get(f, 0.0) for f in REGIME_FEATURES]])
        regime_id = int(self.predict_regime_id(x)[0])
        return self.regime_map.get(regime_id, "choppy_range")

    def predict_regime_proba(self, feature_dict: dict) -> dict[str, float]:
        """Returns probability for each regime."""
        if self.classifier is None:
            raise RuntimeError("Regime classifier not trained")
        x = np.array([[feature_dict.get(f, 0.0) for f in REGIME_FEATURES]])
        proba = self.classifier.predict_proba(self.scaler.transform(x))[0]
        return {
            self.regime_map.get(i, str(i)): float(p)
            for i, p in enumerate(proba)
        }

    def get_multiplier(self, regime_name: str) -> float:
        return REGIME_MULTIPLIERS.get(regime_name, 1.0)

    # ------------------------------------------------------------------
    # Convenience: build regime feature vector from TOS data
    # ------------------------------------------------------------------

    @staticmethod
    def build_regime_features(
        vix_level: float,
        vix_1w_change: float,
        vix_percentile_60d: float,
        spy_return_5d: float,
        spy_return_20d: float,
        spy_rsi_14: float,
        spy_vol_ratio_20d: float,
        watchlist_avg_iv_rank: float,
        watchlist_avg_skew: float,
        spy_term_slope: float,
    ) -> dict:
        return {
            "vix_level": vix_level,
            "vix_1w_change": vix_1w_change,
            "vix_percentile_60d": vix_percentile_60d,
            "spy_return_5d": spy_return_5d,
            "spy_return_20d": spy_return_20d,
            "spy_rsi_14": spy_rsi_14,
            "spy_vol_ratio_20d": spy_vol_ratio_20d,
            "watchlist_avg_iv_rank": watchlist_avg_iv_rank,
            "watchlist_avg_skew": watchlist_avg_skew,
            "spy_term_slope": spy_term_slope,
        }

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self) -> str:
        path = os.path.join(ARTIFACTS_PATH, "regime_model.pkl")
        os.makedirs(ARTIFACTS_PATH, exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump(self, f)
        return path

    @classmethod
    def load(cls) -> "RegimeModel":
        path = os.path.join(ARTIFACTS_PATH, "regime_model.pkl")
        with open(path, "rb") as f:
            return pickle.load(f)
