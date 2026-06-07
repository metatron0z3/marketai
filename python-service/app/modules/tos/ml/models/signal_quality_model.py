"""
Model 1 — Signal Quality Classifier.

Question: Is this unusual volume event informed, or noise?
Target:   quality_signal  (direction correct AND |5d return| > 2%)
"""
import os
import pickle

import lightgbm as lgb
import numpy as np
import shap


ARTIFACTS_PATH = os.getenv("MODEL_ARTIFACTS_PATH", "/app/artifacts")

LGBM_PARAMS = {
    "objective": "binary",
    "metric": ["auc", "binary_logloss"],
    "learning_rate": 0.05,
    "num_leaves": 63,
    "max_depth": 6,
    "min_child_samples": 50,
    "scale_pos_weight": 3,      # quality signals are ~25% of events
    "subsample": 0.8,
    "colsample_bytree": 0.7,
    "reg_alpha": 0.1,
    "reg_lambda": 1.0,
    "n_estimators": 500,
    "random_state": 42,
    "verbose": -1,
}


class SignalQualityModel:
    """LightGBM binary classifier for unusual-volume signal quality."""

    def __init__(self, params: dict | None = None):
        self.params = params or LGBM_PARAMS
        self.model: lgb.LGBMClassifier | None = None
        self.feature_names: list[str] = []

    def fit(
        self,
        X: np.ndarray,
        y: np.ndarray,
        X_val: np.ndarray,
        y_val: np.ndarray,
        feature_names: list[str] | None = None,
    ) -> None:
        if feature_names:
            self.feature_names = feature_names
        self.model = lgb.LGBMClassifier(**self.params)
        self.model.fit(
            X, y,
            eval_set=[(X_val, y_val)],
            callbacks=[
                lgb.early_stopping(stopping_rounds=50, verbose=False),
                lgb.log_evaluation(period=-1),
            ],
        )

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        if self.model is None:
            raise RuntimeError("Model not trained")
        return self.model.predict_proba(X)[:, 1]

    def explain(self, X: np.ndarray) -> dict:
        """Return SHAP values for feature attribution."""
        if self.model is None:
            raise RuntimeError("Model not trained")
        explainer = shap.TreeExplainer(self.model)
        shap_values = explainer.shap_values(X)
        # For binary classifiers lgb returns list[array]; take class-1
        sv = shap_values[1] if isinstance(shap_values, list) else shap_values
        mean_abs = np.abs(sv).mean(axis=0)
        return dict(zip(self.feature_names or range(X.shape[1]), mean_abs))

    def feature_importance(self) -> dict[str, float]:
        if self.model is None:
            raise RuntimeError("Model not trained")
        imp = self.model.feature_importances_
        names = self.feature_names or [f"f{i}" for i in range(len(imp))]
        return dict(sorted(zip(names, imp), key=lambda x: -x[1]))

    def save(self, run_name: str = "signal_quality") -> str:
        path = os.path.join(ARTIFACTS_PATH, f"{run_name}.pkl")
        os.makedirs(ARTIFACTS_PATH, exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump(self, f)
        return path

    @classmethod
    def load(cls, run_name: str = "signal_quality") -> "SignalQualityModel":
        path = os.path.join(ARTIFACTS_PATH, f"{run_name}.pkl")
        with open(path, "rb") as f:
            return pickle.load(f)
