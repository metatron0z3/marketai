import os
import pickle

import torch


ARTIFACTS_PATH = os.getenv("MODEL_ARTIFACTS_PATH", "/app/artifacts")


class SequenceNormalizer:
    """Fit on training data only; applied to val/test and inference."""

    def __init__(self):
        self.mean_: float | None = None
        self.std_: float | None = None

    def fit(self, X):
        import numpy as np
        self.mean_ = X.mean(axis=0)
        self.std_ = X.std(axis=0) + 1e-8
        return self

    def transform(self, X):
        import numpy as np
        return (np.array(X) - self.mean_) / self.std_

    def fit_transform(self, X):
        return self.fit(X).transform(X)


def save_torchscript(model: torch.nn.Module, example_input: torch.Tensor, run_name: str) -> str:
    path = os.path.join(ARTIFACTS_PATH, f"{run_name}_model.pt")
    os.makedirs(ARTIFACTS_PATH, exist_ok=True)
    scripted = torch.jit.trace(model, example_input)
    torch.jit.save(scripted, path)
    return path


def save_normalizer(normalizer: SequenceNormalizer, run_name: str) -> str:
    path = os.path.join(ARTIFACTS_PATH, f"{run_name}_normalizer.pkl")
    os.makedirs(ARTIFACTS_PATH, exist_ok=True)
    with open(path, "wb") as f:
        pickle.dump(normalizer, f)
    return path


def load_torchscript(run_name: str) -> torch.ScriptModule:
    path = os.path.join(ARTIFACTS_PATH, f"{run_name}_model.pt")
    return torch.jit.load(path)


def load_normalizer(run_name: str) -> SequenceNormalizer:
    path = os.path.join(ARTIFACTS_PATH, f"{run_name}_normalizer.pkl")
    with open(path, "rb") as f:
        return pickle.load(f)
