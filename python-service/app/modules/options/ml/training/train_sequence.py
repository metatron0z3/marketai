"""
Phase 2 — LSTM sequence model training.

Run directly:
    python -m app.modules.options.ml.training.train_sequence [--symbol SPY] [--window 20]

Causal temporal model; exports as TorchScript.
"""
import argparse
import os

import mlflow
import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader

from app.modules.options.ml.datasets.options_dataset import SequenceOptionsDataset
from app.modules.options.ml.evaluation.metrics import directional_accuracy, walk_forward_splits
from app.modules.options.ml.features.feature_builder import load_labeled_features, FEATURE_COLS
from app.modules.options.ml.models.base_model import BaseFinancialModel
from app.modules.options.ml.registry.model_registry import (
    SequenceNormalizer,
    save_torchscript,
    save_normalizer,
)

MLFLOW_URI = os.getenv("MLFLOW_TRACKING_URI", "http://mlflow:5000")
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")


class LSTMOptionsModel(BaseFinancialModel):
    def __init__(self, input_size: int, hidden_size: int = 64, num_layers: int = 2, dropout: float = 0.2):
        super().__init__()
        self.lstm = nn.LSTM(
            input_size, hidden_size, num_layers,
            batch_first=True, dropout=dropout if num_layers > 1 else 0.0,
        )
        self.head = nn.Linear(hidden_size, 1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        out, _ = self.lstm(x)
        return self.head(out[:, -1, :]).squeeze(-1)


def train(symbol: str | None = None, window: int = 20, epochs: int = 50, batch_size: int = 64) -> None:
    mlflow.set_tracking_uri(MLFLOW_URI)
    mlflow.set_experiment("options-lstm-sequence")

    X, y = load_labeled_features(symbol)
    if len(X) < window + 50:
        print(f"Insufficient data ({len(X)} rows) for window={window}.")
        return

    normalizer = SequenceNormalizer()
    split = int(0.8 * len(X))
    X_train_norm = normalizer.fit_transform(X[:split])
    X_val_norm = normalizer.transform(X[split:])

    train_ds = SequenceOptionsDataset(X_train_norm, y[:split], window=window)
    val_ds = SequenceOptionsDataset(X_val_norm, y[split:], window=window)
    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=False)
    val_loader = DataLoader(val_ds, batch_size=batch_size)

    model = LSTMOptionsModel(input_size=len(FEATURE_COLS)).to(DEVICE)
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)
    criterion = nn.BCEWithLogitsLoss()

    best_val_loss = float("inf")
    patience_counter = 0
    PATIENCE = 10

    with mlflow.start_run(run_name=f"lstm-{'all' if not symbol else symbol}-w{window}"):
        mlflow.log_params({
            "model": "LSTM",
            "window": window,
            "hidden_size": 64,
            "num_layers": 2,
            "epochs": epochs,
            "symbol": symbol or "all",
        })

        for epoch in range(epochs):
            model.train()
            train_loss = 0.0
            for X_batch, y_batch in train_loader:
                X_batch, y_batch = X_batch.to(DEVICE), y_batch.to(DEVICE)
                optimizer.zero_grad()
                logits = model(X_batch)
                loss = criterion(logits, y_batch)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
                optimizer.step()
                train_loss += loss.item()
            scheduler.step()

            model.eval()
            val_loss = 0.0
            all_preds, all_labels = [], []
            with torch.no_grad():
                for X_batch, y_batch in val_loader:
                    X_batch, y_batch = X_batch.to(DEVICE), y_batch.to(DEVICE)
                    logits = model(X_batch)
                    val_loss += criterion(logits, y_batch).item()
                    all_preds.extend(torch.sigmoid(logits).cpu().numpy())
                    all_labels.extend(y_batch.cpu().numpy())

            avg_val = val_loss / max(len(val_loader), 1)
            acc = directional_accuracy(np.array(all_labels), np.array(all_preds))
            mlflow.log_metrics({"train_loss": train_loss / len(train_loader), "val_loss": avg_val, "val_accuracy": acc}, step=epoch)

            if avg_val < best_val_loss:
                best_val_loss = avg_val
                patience_counter = 0
                best_state = {k: v.clone() for k, v in model.state_dict().items()}
            else:
                patience_counter += 1
                if patience_counter >= PATIENCE:
                    print(f"Early stopping at epoch {epoch}")
                    break

        model.load_state_dict(best_state)
        model.eval().cpu()

        example = torch.zeros(1, window, len(FEATURE_COLS))
        model_path = save_torchscript(model, example, "options_model")
        norm_path = save_normalizer(normalizer, "options_model")
        mlflow.log_artifact(model_path)
        mlflow.log_artifact(norm_path)
        print(f"Saved TorchScript model to {model_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default=None)
    parser.add_argument("--window", type=int, default=20)
    parser.add_argument("--epochs", type=int, default=50)
    args = parser.parse_args()
    train(symbol=args.symbol, window=args.window, epochs=args.epochs)
