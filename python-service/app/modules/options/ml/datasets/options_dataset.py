import numpy as np
import torch
from torch.utils.data import Dataset


class OptionsDataset(Dataset):
    """PyTorch Dataset for tabular options features."""

    def __init__(self, X: np.ndarray, y: np.ndarray):
        self.X = torch.tensor(X, dtype=torch.float32)
        self.y = torch.tensor(y, dtype=torch.float32)

    def __len__(self) -> int:
        return len(self.X)

    def __getitem__(self, idx: int) -> tuple[torch.Tensor, torch.Tensor]:
        return self.X[idx], self.y[idx]


class SequenceOptionsDataset(Dataset):
    """Sliding-window sequence dataset for LSTM/Transformer models."""

    def __init__(self, X: np.ndarray, y: np.ndarray, window: int = 20):
        self.window = window
        sequences, labels = [], []
        for i in range(window, len(X)):
            sequences.append(X[i - window : i])
            labels.append(y[i])
        self.X = torch.tensor(np.array(sequences), dtype=torch.float32)
        self.y = torch.tensor(np.array(labels), dtype=torch.float32)

    def __len__(self) -> int:
        return len(self.X)

    def __getitem__(self, idx: int) -> tuple[torch.Tensor, torch.Tensor]:
        return self.X[idx], self.y[idx]
