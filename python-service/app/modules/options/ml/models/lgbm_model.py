import os
import pickle

import lightgbm as lgb
import numpy as np

from .base_model import BaseFinancialModel

FEATURE_COLS = BaseFinancialModel.FEATURE_COLS


class LGBMOptionsModel:
    """LightGBM wrapper for tabular options signal classification."""

    def __init__(self, params: dict | None = None):
        self.params = params or {
            "objective": "binary",
            "metric": "binary_logloss",
            "learning_rate": 0.05,
            "num_leaves": 31,
            "min_child_samples": 20,
            "n_estimators": 300,
            "random_state": 42,
            "verbose": -1,
        }
        self.model: lgb.LGBMClassifier | None = None

    def fit(self, X: np.ndarray, y: np.ndarray, X_val: np.ndarray, y_val: np.ndarray) -> None:
        self.model = lgb.LGBMClassifier(**self.params)
        self.model.fit(
            X, y,
            eval_set=[(X_val, y_val)],
            callbacks=[lgb.early_stopping(50, verbose=False), lgb.log_evaluation(period=-1)],
        )

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        if self.model is None:
            raise RuntimeError("Model not trained")
        return self.model.predict_proba(X)[:, 1]

    def save(self, path: str) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump(self.model, f)

    @classmethod
    def load(cls, path: str) -> "LGBMOptionsModel":
        instance = cls()
        with open(path, "rb") as f:
            instance.model = pickle.load(f)
        return instance
