"""
Train the EventSequenceTransformer on per-ticker event windows.

Unlike the other models, the sequence model operates over time-ordered groups of events
per ticker. This script constructs those sequences from the labeled signal_catalog data
and trains the Transformer with early stopping.

Sequences are built by:
  1. Grouping signal_catalog rows by symbol
  2. For each row, taking the previous N events (within 5 calendar days) as context
  3. Labeling the sequence as quality=1 if the current event is a quality signal

Label: quality_signal (same as signal quality model)
"""
import argparse
import logging
from collections import defaultdict

import mlflow
import numpy as np
import torch
import torch.nn as nn
from sklearn.metrics import roc_auc_score
from torch.utils.data import DataLoader, Dataset

from app.modules.tos.ml.features.tos_feature_builder import load_training_data
from app.modules.tos.ml.models.sequence_model import (
    MAX_SEQ_LEN,
    SEQ_INPUT_DIM,
    EventSequenceTransformer,
)
from app.modules.tos.ml.training.walk_forward_cv import last_fold_split

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

MLFLOW_EXP  = "tos_sequence"
WINDOW_DAYS = 5
BATCH_SIZE  = 64
MAX_EPOCHS  = 50
LR          = 3e-4
PATIENCE    = 7


class SequenceDataset(Dataset):
    def __init__(self, sequences: list[np.ndarray], quality_labels: np.ndarray,
                 direction_labels: np.ndarray):
        self.sequences = sequences
        self.quality   = quality_labels
        self.direction = direction_labels

    def __len__(self):
        return len(self.sequences)

    def __getitem__(self, idx):
        seq = self.sequences[idx]
        # Pad or truncate to MAX_SEQ_LEN
        if len(seq) > MAX_SEQ_LEN:
            seq = seq[-MAX_SEQ_LEN:]
        pad_len = MAX_SEQ_LEN - len(seq)
        x = np.zeros((MAX_SEQ_LEN, SEQ_INPUT_DIM), dtype=np.float32)
        x[pad_len:] = seq
        pad_mask = np.zeros(MAX_SEQ_LEN + 1, dtype=bool)  # +1 for CLS token
        pad_mask[1:pad_len+1] = True                       # padded slots (after CLS)
        return (
            torch.tensor(x, dtype=torch.float32),
            torch.tensor(pad_mask, dtype=torch.bool),
            torch.tensor(self.quality[idx], dtype=torch.float32),
            torch.tensor(self.direction[idx], dtype=torch.float32),
        )


def _build_sequences(df, feature_cols: list[str]) -> tuple[list, np.ndarray, np.ndarray]:
    """
    For each row, build an event-window sequence from prior same-ticker events
    within WINDOW_DAYS calendar days.
    """
    import pandas as pd
    df = df.sort_values("detected_at").reset_index(drop=True)
    df["detected_at"] = pd.to_datetime(df["detected_at"])

    by_symbol = defaultdict(list)
    for i, row in df.iterrows():
        by_symbol[row["symbol"]].append(i)

    sequences, quality_labels, direction_labels = [], [], []
    X_all = df[feature_cols].fillna(0).values

    for symbol, indices in by_symbol.items():
        for pos, cur_idx in enumerate(indices):
            cur_time = df.loc[cur_idx, "detected_at"]
            cutoff   = cur_time - pd.Timedelta(days=WINDOW_DAYS)
            # Events strictly before current event within window
            window = [
                i for i in indices[:pos]
                if df.loc[i, "detected_at"] >= cutoff
            ]
            window_features = X_all[window]      # (n_prior_events, n_features)
            cur_features    = X_all[[cur_idx]]   # include current as final step
            seq = np.concatenate([window_features, cur_features], axis=0)
            sequences.append(seq[:, :SEQ_INPUT_DIM])
            quality_labels.append(int(df.loc[cur_idx].get("quality_signal", 0)))
            direction_labels.append(int(df.loc[cur_idx].get("direction_correct_5d", 0)))

    return sequences, np.array(quality_labels), np.array(direction_labels)


def run_training(
    symbol: str | None = None,
    min_rows: int = 100,
    dry_run: bool = False,
) -> dict:
    df = load_training_data(min_labeled_days=5, min_rows=min_rows, symbol=symbol)

    feature_cols = [c for c in df.columns
                    if c not in ("signal_id", "symbol", "detected_at", "quality_signal",
                                 "direction_correct_5d", "underlying_return_1d_fwd",
                                 "underlying_return_5d_fwd", "option_return_5d")]
    feature_cols = feature_cols[:SEQ_INPUT_DIM]  # cap to model input dim

    log.info("Building event sequences (symbol=%s)...", symbol or "all")
    sequences, qual_labels, dir_labels = _build_sequences(df, feature_cols)
    log.info("Built %d sequences, %.1f%% quality", len(sequences), qual_labels.mean() * 100)

    train_df, val_df = last_fold_split(df, val_months=2)
    train_mask = df.index.isin(train_df.index)
    val_mask   = df.index.isin(val_df.index)

    sequences   = np.array(sequences, dtype=object)
    train_seqs  = sequences[train_mask].tolist()
    val_seqs    = sequences[val_mask].tolist()
    train_qual  = qual_labels[train_mask]
    val_qual    = qual_labels[val_mask]
    train_dir   = dir_labels[train_mask]
    val_dir     = dir_labels[val_mask]

    train_ds = SequenceDataset(train_seqs, train_qual, train_dir)
    val_ds   = SequenceDataset(val_seqs,   val_qual,   val_dir)
    train_dl = DataLoader(train_ds, batch_size=BATCH_SIZE, shuffle=True)
    val_dl   = DataLoader(val_ds,   batch_size=BATCH_SIZE, shuffle=False)

    if dry_run:
        return {"status": "dry_run", "n_sequences": len(sequences)}

    model = EventSequenceTransformer()
    optimizer = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=1e-4)
    qual_loss_fn = nn.BCELoss()
    dir_loss_fn  = nn.BCELoss()

    mlflow.set_experiment(MLFLOW_EXP)
    run_name = f"sequence{'_' + symbol if symbol else ''}"

    best_val_auc = 0.0
    patience_ctr = 0

    with mlflow.start_run(run_name=run_name):
        mlflow.log_params({
            "symbol": symbol or "all", "max_epochs": MAX_EPOCHS,
            "batch_size": BATCH_SIZE, "lr": LR, "window_days": WINDOW_DAYS,
        })

        for epoch in range(MAX_EPOCHS):
            model.train()
            epoch_loss = 0.0
            for x, mask, q_lbl, d_lbl in train_dl:
                optimizer.zero_grad()
                _, qual, dirn = model(x, mask)
                loss = qual_loss_fn(qual, q_lbl) + 0.5 * dir_loss_fn(dirn, d_lbl)
                loss.backward()
                nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                optimizer.step()
                epoch_loss += loss.item()

            model.eval()
            val_proba, val_true = [], []
            with torch.no_grad():
                for x, mask, q_lbl, _ in val_dl:
                    _, qual, _ = model(x, mask)
                    val_proba.extend(qual.numpy())
                    val_true.extend(q_lbl.numpy())

            val_auc = roc_auc_score(val_true, val_proba) if len(set(val_true)) > 1 else 0.5
            mlflow.log_metrics({"val_auc": val_auc, "train_loss": epoch_loss}, step=epoch)
            log.info("Epoch %d: loss=%.4f val_auc=%.3f", epoch, epoch_loss, val_auc)

            if val_auc > best_val_auc:
                best_val_auc = val_auc
                path = model.save()
                patience_ctr = 0
            else:
                patience_ctr += 1
                if patience_ctr >= PATIENCE:
                    log.info("Early stopping at epoch %d", epoch)
                    break

        mlflow.log_metric("best_val_auc", best_val_auc)
        mlflow.log_artifact(path)
        log.info("Best val AUC=%.3f — model saved to %s", best_val_auc, path)

    return {"status": "ok", "best_val_auc": best_val_auc, "artifact": path}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default=None)
    parser.add_argument("--min-rows", type=int, default=100)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run_training(args.symbol, args.min_rows, args.dry_run)


if __name__ == "__main__":
    main()
