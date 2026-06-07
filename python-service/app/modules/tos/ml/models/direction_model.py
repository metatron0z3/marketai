"""
Model 2 — Direction Predictor.

Question: Given unusual volume, will the underlying move in the option's direction?
Target:   direction_correct_5d (1 = correct, 0 = wrong)
Trained separately for calls and puts.
"""
import os
import pickle

import numpy as np
import xgboost as xgb

from app.modules.tos.ml.features.tos_feature_builder import DIRECTION_FEATURES


ARTIFACTS_PATH = os.getenv("MODEL_ARTIFACTS_PATH", "/app/artifacts")

XGB_PARAMS = {
    "objective": "binary:logistic",
    "eval_metric": "auc",
    "eta": 0.05,
    "max_depth": 5,
    "min_child_weight": 30,
    "subsample": 0.8,
    "colsample_bytree": 0.7,
    "scale_pos_weight": 1.2,   # slight upweight: market has upward drift
    "n_estimators": 400,
    "random_state": 42,
    "verbosity": 0,
}


class DirectionModel:
    """
    XGBoost direction predictor.

    Trained per option_type so the model learns direction-conditional context
    rather than re-learning what a call vs put already encodes.
    """

    def __init__(self, option_type: str, params: dict | None = None):
        assert option_type in ("C", "P"), "option_type must be 'C' or 'P'"
        self.option_type = option_type
        self.params = params or XGB_PARAMS
        self.model: xgb.XGBClassifier | None = None
        self.feature_names: list[str] = DIRECTION_FEATURES

    def fit(
        self,
        X: np.ndarray,
        y: np.ndarray,
        X_val: np.ndarray,
        y_val: np.ndarray,
    ) -> None:
        self.model = xgb.XGBClassifier(**self.params)
        self.model.fit(
            X, y,
            eval_set=[(X_val, y_val)],
            verbose=False,
        )

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """Returns P(direction correct)."""
        if self.model is None:
            raise RuntimeError("Model not trained")
        return self.model.predict_proba(X)[:, 1]

    def save(self) -> str:
        name = f"direction_{self.option_type.lower()}"
        path = os.path.join(ARTIFACTS_PATH, f"{name}.pkl")
        os.makedirs(ARTIFACTS_PATH, exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump(self, f)
        return path

    @classmethod
    def load(cls, option_type: str) -> "DirectionModel":
        name = f"direction_{option_type.lower()}"
        path = os.path.join(ARTIFACTS_PATH, f"{name}.pkl")
        with open(path, "rb") as f:
            return pickle.load(f)
