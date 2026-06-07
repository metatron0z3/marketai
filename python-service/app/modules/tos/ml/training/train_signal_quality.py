"""
Train the Signal Quality model (LightGBM binary classifier).

Walk-forward cross-validation over calendar months; MLflow tracking.
Label: quality_signal = 1 if direction_correct_5d AND |underlying_return_5d_fwd| > 0.02

Usage:
    python -m app.modules.tos.ml.training.train_signal_quality
    python -m app.modules.tos.ml.training.train_signal_quality --symbol TSLA
    python -m app.modules.tos.ml.training.train_signal_quality --min-rows 200
"""
import argparse
import logging

import mlflow
import numpy as np
from sklearn.metrics import (
    average_precision_score,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

from app.modules.tos.ml.features.tos_feature_builder import (
    ALL_FEATURES,
    load_training_data,
)
from app.modules.tos.ml.models.signal_quality_model import SignalQualityModel
from app.modules.tos.ml.training.walk_forward_cv import (
    summarize_folds,
    time_based_walk_forward,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

LABEL_COL   = "quality_signal"
MLFLOW_EXP  = "tos_signal_quality"


def _compute_label(df):
    """Derive quality_signal if not pre-computed in signal_catalog."""
    if LABEL_COL in df.columns:
        return df
    if "direction_correct_5d" in df.columns and "underlying_return_5d_fwd" in df.columns:
        df = df.copy()
        df[LABEL_COL] = (
            (df["direction_correct_5d"] == 1)
            & (df["underlying_return_5d_fwd"].abs() > 0.02)
        ).astype(int)
    else:
        raise ValueError("Cannot derive quality_signal: missing follow-through columns")
    return df


def run_training(
    symbol: str | None = None,
    min_rows: int = 100,
    val_months: int = 1,
    gap_months: int = 0,
    dry_run: bool = False,
) -> dict:
    log.info("Loading training data (symbol=%s)", symbol or "all")
    df = load_training_data(min_labeled_days=5, min_rows=min_rows, symbol=symbol)
    df = _compute_label(df)

    feature_cols = [f for f in ALL_FEATURES if f in df.columns]
    X = df[feature_cols].fillna(0).values
    y = df[LABEL_COL].values

    log.info("Dataset: %d rows, %d features, %.1f%% quality signals",
             len(df), len(feature_cols), y.mean() * 100)

    folds = time_based_walk_forward(
        df, timestamp_col="detected_at", val_months=val_months, gap_months=gap_months
    )
    log.info(summarize_folds(folds))

    mlflow.set_experiment(MLFLOW_EXP)
    run_name = f"signal_quality{'_' + symbol if symbol else ''}"

    fold_metrics: list[dict] = []
    with mlflow.start_run(run_name=run_name):
        mlflow.log_params({
            "symbol": symbol or "all",
            "n_features": len(feature_cols),
            "n_folds": len(folds),
            "val_months": val_months,
            "gap_months": gap_months,
            "label": LABEL_COL,
        })

        for fold in folds:
            X_tr, y_tr = X[fold.train_idx], y[fold.train_idx]
            X_vl, y_vl = X[fold.val_idx],   y[fold.val_idx]

            if dry_run:
                log.info("Dry-run: skipping fold %d fit", fold.fold_num)
                continue

            model = SignalQualityModel()
            model.fit(X_tr, y_tr, X_vl, y_vl, feature_names=feature_cols)

            proba = model.predict_proba(X_vl)
            preds = (proba >= 0.5).astype(int)

            m = {
                "fold": fold.fold_num,
                "auc":  roc_auc_score(y_vl, proba) if y_vl.sum() > 0 else 0.0,
                "ap":   average_precision_score(y_vl, proba) if y_vl.sum() > 0 else 0.0,
                "f1":   f1_score(y_vl, preds, zero_division=0),
                "precision": precision_score(y_vl, preds, zero_division=0),
                "recall":    recall_score(y_vl, preds, zero_division=0),
                "n_val": len(y_vl),
                "pct_pos_val": float(y_vl.mean()),
            }
            fold_metrics.append(m)
            log.info("Fold %d: AUC=%.3f AP=%.3f F1=%.3f", m["fold"], m["auc"], m["ap"], m["f1"])

        if fold_metrics and not dry_run:
            avg = {k: float(np.mean([fm[k] for fm in fold_metrics]))
                   for k in ("auc", "ap", "f1", "precision", "recall")}
            mlflow.log_metrics({f"cv_mean_{k}": v for k, v in avg.items()})
            log.info("CV means: %s", {k: f"{v:.3f}" for k, v in avg.items()})

            # Train final model on all data using last fold for early stopping
            last_fold = folds[-1]
            X_vl_last, y_vl_last = X[last_fold.val_idx], y[last_fold.val_idx]
            final_model = SignalQualityModel()
            final_model.fit(X, y, X_vl_last, y_vl_last, feature_names=feature_cols)
            artifact_path = final_model.save(run_name=run_name)
            mlflow.log_artifact(artifact_path)
            log.info("Saved model to %s", artifact_path)

            return {"status": "ok", "cv_metrics": avg, "artifact": artifact_path}

    return {"status": "dry_run" if dry_run else "no_folds"}


def main():
    parser = argparse.ArgumentParser(description="Train TOS signal quality model")
    parser.add_argument("--symbol", default=None)
    parser.add_argument("--min-rows", type=int, default=100)
    parser.add_argument("--val-months", type=int, default=1)
    parser.add_argument("--gap-months", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    result = run_training(
        symbol=args.symbol,
        min_rows=args.min_rows,
        val_months=args.val_months,
        gap_months=args.gap_months,
        dry_run=args.dry_run,
    )
    print(result)


if __name__ == "__main__":
    main()
