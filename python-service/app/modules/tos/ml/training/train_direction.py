"""
Train Direction models (XGBoost) — separate for calls and puts.

Walk-forward CV, MLflow tracking.
Label: direction_correct_5d (1 = underlying moved in option's implied direction)
"""
import argparse
import logging

import mlflow
import numpy as np
from sklearn.metrics import average_precision_score, f1_score, roc_auc_score

from app.modules.tos.ml.features.tos_feature_builder import (
    DIRECTION_FEATURES,
    load_training_data,
)
from app.modules.tos.ml.models.direction_model import DirectionModel
from app.modules.tos.ml.training.walk_forward_cv import (
    summarize_folds,
    time_based_walk_forward,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

LABEL_COL  = "direction_correct_5d"
MLFLOW_EXP = "tos_direction"


def run_training(
    option_type: str,
    symbol: str | None = None,
    min_rows: int = 80,
    val_months: int = 1,
    dry_run: bool = False,
) -> dict:
    assert option_type in ("C", "P")
    log.info("Training direction model: option_type=%s symbol=%s", option_type, symbol or "all")

    df = load_training_data(min_labeled_days=5, min_rows=min_rows, symbol=symbol)
    if LABEL_COL not in df.columns:
        raise ValueError(f"Missing label column: {LABEL_COL}")

    df = df[df["option_type"] == option_type].copy()
    if len(df) < min_rows:
        log.warning("Only %d rows for option_type=%s — skipping", len(df), option_type)
        return {"status": "insufficient_data"}

    feature_cols = [f for f in DIRECTION_FEATURES if f in df.columns]
    X = df[feature_cols].fillna(0).values
    y = df[LABEL_COL].values

    log.info("Dataset (%s): %d rows, %d features, %.1f%% direction correct",
             option_type, len(df), len(feature_cols), y.mean() * 100)

    folds = time_based_walk_forward(df, val_months=val_months)
    log.info(summarize_folds(folds))

    mlflow.set_experiment(MLFLOW_EXP)
    run_name = f"direction_{option_type.lower()}{'_' + symbol if symbol else ''}"

    fold_metrics: list[dict] = []
    with mlflow.start_run(run_name=run_name):
        mlflow.log_params({
            "option_type": option_type, "symbol": symbol or "all",
            "n_features": len(feature_cols), "n_folds": len(folds),
        })

        for fold in folds:
            X_tr, y_tr = X[fold.train_idx], y[fold.train_idx]
            X_vl, y_vl = X[fold.val_idx],   y[fold.val_idx]

            if dry_run:
                continue

            model = DirectionModel(option_type=option_type)
            model.fit(X_tr, y_tr, X_vl, y_vl)

            proba = model.predict_proba(X_vl)
            fold_metrics.append({
                "fold": fold.fold_num,
                "auc":  roc_auc_score(y_vl, proba) if len(set(y_vl)) > 1 else 0.5,
                "ap":   average_precision_score(y_vl, proba) if y_vl.sum() > 0 else 0.0,
                "f1":   f1_score(y_vl, (proba >= 0.5).astype(int), zero_division=0),
            })
            log.info("Fold %d: AUC=%.3f", fold.fold_num, fold_metrics[-1]["auc"])

        if fold_metrics and not dry_run:
            avg = {k: float(np.mean([fm[k] for fm in fold_metrics]))
                   for k in ("auc", "ap", "f1")}
            mlflow.log_metrics({f"cv_mean_{k}": v for k, v in avg.items()})

            last_fold = folds[-1]
            final = DirectionModel(option_type=option_type)
            final.fit(X, y, X[last_fold.val_idx], y[last_fold.val_idx])
            path = final.save()
            mlflow.log_artifact(path)
            log.info("Saved %s direction model to %s", option_type, path)
            return {"status": "ok", "cv_metrics": avg, "artifact": path}

    return {"status": "dry_run" if dry_run else "no_folds"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--option-type", choices=["C", "P", "both"], default="both")
    parser.add_argument("--symbol", default=None)
    parser.add_argument("--min-rows", type=int, default=80)
    parser.add_argument("--val-months", type=int, default=1)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    types = ["C", "P"] if args.option_type == "both" else [args.option_type]
    for ot in types:
        run_training(ot, args.symbol, args.min_rows, args.val_months, args.dry_run)


if __name__ == "__main__":
    main()
