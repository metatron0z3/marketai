"""
Phase 1 — LightGBM baseline training.

Run directly:
    python -m app.modules.options.ml.training.train_lgbm [--symbol SPY]

Walk-forward cross-validation; logs to MLflow.
"""
import argparse
import os

import mlflow
import numpy as np

from app.modules.options.ml.evaluation.metrics import (
    directional_accuracy,
    walk_forward_splits,
)
from app.modules.options.ml.features.feature_builder import load_labeled_features, FEATURE_COLS
from app.modules.options.ml.models.lgbm_model import LGBMOptionsModel
from app.modules.options.ml.registry.model_registry import (
    SequenceNormalizer,
    save_normalizer,
)

MLFLOW_URI = os.getenv("MLFLOW_TRACKING_URI", "http://mlflow:5000")
ARTIFACTS_PATH = os.getenv("MODEL_ARTIFACTS_PATH", "/app/artifacts")


def train(symbol: str | None = None, n_splits: int = 5) -> None:
    mlflow.set_tracking_uri(MLFLOW_URI)
    mlflow.set_experiment("options-lgbm-baseline")

    X, y = load_labeled_features(symbol)
    if len(X) < 100:
        print(f"Insufficient data ({len(X)} rows). Need at least 100 labeled rows.")
        return

    splits = walk_forward_splits(len(X), n_splits=n_splits)
    fold_scores = []

    with mlflow.start_run(run_name=f"lgbm-{'all' if not symbol else symbol}"):
        mlflow.log_params({
            "model": "LightGBM",
            "features": FEATURE_COLS,
            "n_splits": n_splits,
            "symbol": symbol or "all",
        })

        for fold_idx, (train_idx, val_idx) in enumerate(splits):
            X_train, y_train = X[train_idx], y[train_idx]
            X_val, y_val = X[val_idx], y[val_idx]

            # Fit normalizer on train split only
            normalizer = SequenceNormalizer()
            X_train_norm = normalizer.fit_transform(X_train)
            X_val_norm = normalizer.transform(X_val)

            model = LGBMOptionsModel()
            model.fit(X_train_norm, y_train, X_val_norm, y_val)

            preds = model.predict_proba(X_val_norm)
            acc = directional_accuracy(y_val, preds)
            fold_scores.append(acc)
            mlflow.log_metric(f"fold_{fold_idx}_accuracy", acc)
            print(f"Fold {fold_idx}: accuracy={acc:.4f}")

        mean_acc = np.mean(fold_scores)
        mlflow.log_metric("mean_accuracy", mean_acc)
        print(f"Mean walk-forward accuracy: {mean_acc:.4f}")

        # Retrain on all data for the final saved model
        normalizer = SequenceNormalizer()
        X_norm = normalizer.fit_transform(X)
        final_model = LGBMOptionsModel()
        # Split 80/20 for final train
        split = int(0.8 * len(X_norm))
        final_model.fit(X_norm[:split], y[:split], X_norm[split:], y[split:])

        model_path = os.path.join(ARTIFACTS_PATH, "options_model.pkl")
        final_model.save(model_path)
        norm_path = save_normalizer(normalizer, "options_model")

        mlflow.log_artifact(model_path)
        mlflow.log_artifact(norm_path)
        print(f"Saved model to {model_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default=None, help="Filter training data to one symbol")
    parser.add_argument("--splits", type=int, default=5)
    args = parser.parse_args()
    train(symbol=args.symbol, n_splits=args.splits)
