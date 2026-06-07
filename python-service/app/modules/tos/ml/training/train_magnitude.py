"""
Train the Magnitude model (3-head quantile regression LightGBM).

Target: underlying_return_5d_fwd (continuous)
Quantiles: q10, q50, q90
"""
import argparse
import logging

import mlflow
import numpy as np
from sklearn.metrics import mean_absolute_error

from app.modules.tos.ml.features.tos_feature_builder import (
    ALL_FEATURES,
    load_training_data,
)
from app.modules.tos.ml.models.magnitude_model import MagnitudeModel
from app.modules.tos.ml.training.walk_forward_cv import (
    summarize_folds,
    time_based_walk_forward,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

TARGET_COL = "underlying_return_5d_fwd"
MLFLOW_EXP = "tos_magnitude"


def _pinball(y_true, y_pred, alpha):
    """Pinball / quantile loss."""
    delta = y_true - y_pred
    return float(np.mean(np.where(delta >= 0, alpha * delta, (alpha - 1) * delta)))


def run_training(
    symbol: str | None = None,
    min_rows: int = 100,
    val_months: int = 1,
    dry_run: bool = False,
) -> dict:
    log.info("Loading data for magnitude model (symbol=%s)", symbol or "all")
    df = load_training_data(min_labeled_days=5, min_rows=min_rows, symbol=symbol)

    if TARGET_COL not in df.columns:
        raise ValueError(f"Missing target column: {TARGET_COL}")

    feature_cols = [f for f in ALL_FEATURES if f in df.columns]
    X = df[feature_cols].fillna(0).values
    y = df[TARGET_COL].values.astype(float)

    log.info("Dataset: %d rows, target mean=%.4f std=%.4f", len(df), y.mean(), y.std())

    folds = time_based_walk_forward(df, val_months=val_months)
    log.info(summarize_folds(folds))

    mlflow.set_experiment(MLFLOW_EXP)
    run_name = f"magnitude{'_' + symbol if symbol else ''}"

    fold_metrics: list[dict] = []
    with mlflow.start_run(run_name=run_name):
        mlflow.log_params({
            "symbol": symbol or "all",
            "n_features": len(feature_cols),
            "n_folds": len(folds),
            "target": TARGET_COL,
        })

        for fold in folds:
            X_tr, y_tr = X[fold.train_idx], y[fold.train_idx]
            X_vl, y_vl = X[fold.val_idx],   y[fold.val_idx]

            if dry_run:
                continue

            model = MagnitudeModel()
            model.fit(X_tr, y_tr, X_vl, y_vl)

            q10, q50, q90 = model.predict(X_vl)
            coverage = float(np.mean((y_vl >= q10) & (y_vl <= q90)))
            m = {
                "fold":     fold.fold_num,
                "mae_q50":  mean_absolute_error(y_vl, q50),
                "pb_q10":   _pinball(y_vl, q10, 0.10),
                "pb_q50":   _pinball(y_vl, q50, 0.50),
                "pb_q90":   _pinball(y_vl, q90, 0.90),
                "coverage_80": coverage,
            }
            fold_metrics.append(m)
            log.info("Fold %d: MAE(q50)=%.4f coverage_80=%.2f%%",
                     m["fold"], m["mae_q50"], coverage * 100)

        if fold_metrics and not dry_run:
            avg = {k: float(np.mean([fm[k] for fm in fold_metrics]))
                   for k in ("mae_q50", "pb_q10", "pb_q50", "pb_q90", "coverage_80")}
            mlflow.log_metrics({f"cv_mean_{k}": v for k, v in avg.items()})
            log.info("CV means: %s", {k: f"{v:.4f}" for k, v in avg.items()})

            last_fold = folds[-1]
            final = MagnitudeModel()
            final.fit(X, y, X[last_fold.val_idx], y[last_fold.val_idx])
            path = final.save()
            mlflow.log_artifact(path)
            log.info("Saved magnitude model to %s", path)
            return {"status": "ok", "cv_metrics": avg, "artifact": path}

    return {"status": "dry_run" if dry_run else "no_folds"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default=None)
    parser.add_argument("--min-rows", type=int, default=100)
    parser.add_argument("--val-months", type=int, default=1)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run_training(args.symbol, args.min_rows, args.val_months, args.dry_run)


if __name__ == "__main__":
    main()
