"""
Time-based walk-forward cross-validation for TOS signal models.

Unlike the index-based walk_forward_splits in options/ml/evaluation/metrics.py,
this uses calendar months so each fold has a fixed time gap between train and val.
This is strictly necessary for financial time-series: shuffled or index-based splits
allow look-ahead through lagged features computed over the full dataset.

Fold structure (expanding window):
  Train: [start, fold_end - gap]
  Val:   [fold_end, fold_end + val_months]
  Gap:   gap_months between train and val prevents leakage from lagged features

Minimum 3 folds required; fewer raises ValueError.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import numpy as np
import pandas as pd


@dataclass
class CVFold:
    fold_num: int
    train_idx: np.ndarray
    val_idx: np.ndarray
    train_start: datetime
    train_end: datetime
    val_start: datetime
    val_end: datetime

    def __repr__(self) -> str:
        ts = self.train_start.strftime("%Y-%m")
        te = self.train_end.strftime("%Y-%m")
        vs = self.val_start.strftime("%Y-%m")
        ve = self.val_end.strftime("%Y-%m")
        return (
            f"Fold {self.fold_num}: train [{ts}→{te}] n={len(self.train_idx)}"
            f" | val [{vs}→{ve}] n={len(self.val_idx)}"
        )


def time_based_walk_forward(
    df: pd.DataFrame,
    timestamp_col: str = "detected_at",
    min_train_months: int = 3,
    val_months: int = 1,
    gap_months: int = 0,
    step_months: int = 1,
) -> list[CVFold]:
    """
    Generate expanding-window walk-forward folds from a time-indexed DataFrame.

    Args:
        df:               DataFrame with a datetime column `timestamp_col`.
        timestamp_col:    Name of the datetime column (tz-aware or naive).
        min_train_months: Minimum months of history before first fold.
        val_months:       Validation window length in months.
        gap_months:       Gap between train end and val start (prevents leakage
                          from features computed with a rolling look-back window).
        step_months:      How many months to advance train end per fold.

    Returns:
        List of CVFold objects, each with integer index arrays into df.

    Raises:
        ValueError: If fewer than 3 folds can be generated from the data.
    """
    timestamps = pd.to_datetime(df[timestamp_col])
    # Normalize to month-start for consistent period arithmetic
    months = timestamps.dt.to_period("M")
    all_months = sorted(months.unique())

    if len(all_months) < min_train_months + gap_months + val_months + 1:
        raise ValueError(
            f"Not enough data: need at least "
            f"{min_train_months + gap_months + val_months + 1} months, "
            f"got {len(all_months)}"
        )

    folds: list[CVFold] = []
    fold_num = 0

    # First fold: train = first min_train_months, then step forward by step_months
    train_end_idx = min_train_months - 1  # index into all_months

    while True:
        val_start_idx = train_end_idx + 1 + gap_months
        val_end_idx   = val_start_idx + val_months - 1

        if val_end_idx >= len(all_months):
            break

        train_period_start = all_months[0]
        train_period_end   = all_months[train_end_idx]
        val_period_start   = all_months[val_start_idx]
        val_period_end     = all_months[val_end_idx]

        train_mask = (months >= train_period_start) & (months <= train_period_end)
        val_mask   = (months >= val_period_start)   & (months <= val_period_end)

        train_idx = np.where(train_mask)[0]
        val_idx   = np.where(val_mask)[0]

        if len(train_idx) > 0 and len(val_idx) > 0:
            folds.append(CVFold(
                fold_num=fold_num,
                train_idx=train_idx,
                val_idx=val_idx,
                train_start=train_period_start.start_time,
                train_end=train_period_end.end_time,
                val_start=val_period_start.start_time,
                val_end=val_period_end.end_time,
            ))
            fold_num += 1

        train_end_idx += step_months

    if len(folds) < 3:
        raise ValueError(
            f"Only {len(folds)} fold(s) generated — need at least 3. "
            f"Collect more data or reduce min_train_months."
        )

    return folds


def summarize_folds(folds: list[CVFold]) -> str:
    lines = [f"Walk-forward CV: {len(folds)} folds"]
    for f in folds:
        lines.append(f"  {f}")
    return "\n".join(lines)


def last_fold_split(
    df: pd.DataFrame,
    timestamp_col: str = "detected_at",
    val_months: int = 2,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Simple train/val split using the last val_months as holdout.
    Useful for final model training when you want one canonical split.
    """
    timestamps = pd.to_datetime(df[timestamp_col])
    cutoff = timestamps.max() - pd.DateOffset(months=val_months)
    train = df[timestamps <= cutoff].copy()
    val   = df[timestamps > cutoff].copy()
    return train, val
