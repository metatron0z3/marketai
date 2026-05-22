import numpy as np


def directional_accuracy(y_true: np.ndarray, y_pred: np.ndarray, threshold: float = 0.5) -> float:
    predicted_labels = (y_pred >= threshold).astype(int)
    return float(np.mean(predicted_labels == y_true))


def sharpe_ratio(returns: np.ndarray, annualization: int = 252) -> float:
    if returns.std() == 0:
        return 0.0
    return float((returns.mean() / returns.std()) * np.sqrt(annualization))


def max_drawdown(equity_curve: np.ndarray) -> float:
    peak = np.maximum.accumulate(equity_curve)
    drawdown = (equity_curve - peak) / np.maximum(peak, 1e-9)
    return float(drawdown.min())


def walk_forward_splits(n: int, n_splits: int = 5) -> list[tuple[np.ndarray, np.ndarray]]:
    """Return (train_idx, val_idx) pairs using expanding walk-forward windows."""
    fold_size = n // (n_splits + 1)
    splits = []
    for i in range(1, n_splits + 1):
        train_end = fold_size * i
        val_end = min(train_end + fold_size, n)
        train_idx = np.arange(0, train_end)
        val_idx = np.arange(train_end, val_end)
        if len(val_idx) > 0:
            splits.append((train_idx, val_idx))
    return splits
