"""
Model 3 — Magnitude Estimator.

Question: How big will the move be?
Target:   underlying_return_5d_fwd (continuous regression)

Three quantile heads: q10 (pessimistic), q50 (median), q90 (optimistic).
Output: (expected_return, lower_bound, upper_bound) — a move distribution.
"""
import os
import pickle

import lightgbm as lgb
import numpy as np

from app.modules.tos.ml.features.tos_feature_builder import ALL_FEATURES


ARTIFACTS_PATH = os.getenv("MODEL_ARTIFACTS_PATH", "/app/artifacts")
QUANTILES = [0.10, 0.50, 0.90]

_BASE_PARAMS = {
    "n_estimators": 300,
    "learning_rate": 0.05,
    "num_leaves": 31,
    "min_child_samples": 50,
    "subsample": 0.8,
    "colsample_bytree": 0.7,
    "random_state": 42,
    "verbose": -1,
}


class MagnitudeModel:
    """
    Three quantile-regression heads over the same feature set.

    predict() returns (q10, q50, q90) — the 80% confidence interval
    for the 5-day return following the unusual volume event.
    """

    def __init__(self):
        self.models: dict[float, lgb.LGBMRegressor] = {}
        self.feature_names: list[str] = ALL_FEATURES

    def fit(
        self,
        X: np.ndarray,
        y: np.ndarray,
        X_val: np.ndarray | None = None,
        y_val: np.ndarray | None = None,
    ) -> None:
        for alpha in QUANTILES:
            params = {**_BASE_PARAMS, "objective": "quantile", "alpha": alpha}
            m = lgb.LGBMRegressor(**params)
            if X_val is not None:
                m.fit(X, y, eval_set=[(X_val, y_val)],
                      callbacks=[lgb.early_stopping(30, verbose=False),
                                 lgb.log_evaluation(-1)])
            else:
                m.fit(X, y)
            self.models[alpha] = m

    def predict(self, X: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Returns (q10, q50, q90) arrays."""
        if not self.models:
            raise RuntimeError("Model not trained")
        q10 = self.models[0.10].predict(X)
        q50 = self.models[0.50].predict(X)
        q90 = self.models[0.90].predict(X)
        return q10, q50, q90

    def prob_exceeds(self, X: np.ndarray, threshold: float = 0.02) -> np.ndarray:
        """
        Approximate P(|return_5d| > threshold) using the quantile spread.
        Assumes symmetric normal around q50 with std estimated from q90-q50.
        """
        from scipy.stats import norm
        _, q50, q90 = self.predict(X)
        sigma = np.abs(q90 - q50) / norm.ppf(0.90) + 1e-8
        p_up   = 1 - norm.cdf(threshold, loc=q50, scale=sigma)
        p_down = norm.cdf(-threshold, loc=q50, scale=sigma)
        return p_up + p_down

    def save(self) -> str:
        path = os.path.join(ARTIFACTS_PATH, "magnitude_model.pkl")
        os.makedirs(ARTIFACTS_PATH, exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump(self, f)
        return path

    @classmethod
    def load(cls) -> "MagnitudeModel":
        path = os.path.join(ARTIFACTS_PATH, "magnitude_model.pkl")
        with open(path, "rb") as f:
            return pickle.load(f)
