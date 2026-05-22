import torch
import torch.nn as nn


class BaseFinancialModel(nn.Module):
    """Base class for all options ML models."""

    FEATURE_COLS = [
        "rvol", "vol_oi_ratio", "premium_flow", "sweep_intensity",
        "aggressor_ratio", "delta_exposure", "iv_rank", "days_to_exp",
    ]

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        raise NotImplementedError
