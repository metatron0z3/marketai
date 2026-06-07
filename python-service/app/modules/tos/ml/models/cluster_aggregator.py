"""
Model 5 — Multi-Strike Cluster Aggregator.

Question: When N contracts fire together in a cluster, which ones carry signal
          and what does the aggregate pattern imply?

Architecture: Attention-weighted aggregation (Set Transformer lite).
Input:  (batch, n_contracts, feature_dim) — variable-length set of contract features
Output: (batch, hidden_dim) — single aggregate vector per cluster, plus attention weights

The aggregated vector is then passed as additional features into SignalQualityModel
for cluster events, or used on its own as a cluster-level quality score.
"""
import os

import numpy as np
import torch
import torch.nn as nn


ARTIFACTS_PATH = os.getenv("MODEL_ARTIFACTS_PATH", "/app/artifacts")
CLUSTER_INPUT_DIM = 20   # subset of CONTRACT_FEATURES relevant per individual contract


class ClusterAggregator(nn.Module):
    """
    Attention-based aggregation of multi-strike unusual volume clusters.

    Learns which contracts in a cluster carry the most informative signal.
    An OTM sweep with high volume_ratio should dominate over an ATM print
    with moderate volume — the attention weights capture this.
    """

    def __init__(
        self,
        input_dim: int = CLUSTER_INPUT_DIM,
        hidden_dim: int = 64,
        output_dim: int = 32,
    ):
        super().__init__()
        self.attention = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.Tanh(),
            nn.Linear(hidden_dim, 1),
        )
        self.encoder = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, output_dim),
        )
        # Binary quality head (trained on cluster labels)
        self.quality_head = nn.Sequential(
            nn.Linear(output_dim, 16),
            nn.ReLU(),
            nn.Linear(16, 1),
            nn.Sigmoid(),
        )

    def forward(
        self,
        x: torch.Tensor,
        pad_mask: torch.Tensor | None = None,
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """
        Args:
            x:        (batch, n_contracts, input_dim)
            pad_mask: (batch, n_contracts) True where padded (ignored)

        Returns:
            aggregate:      (batch, output_dim) — cluster-level representation
            attn_weights:   (batch, n_contracts) — which contracts dominated
            quality_score:  (batch,) — cluster quality in [0,1]
        """
        raw_attn = self.attention(x).squeeze(-1)       # (batch, n_contracts)
        if pad_mask is not None:
            raw_attn = raw_attn.masked_fill(pad_mask, float("-inf"))
        attn_weights = torch.softmax(raw_attn, dim=-1)  # (batch, n_contracts)

        encoded = self.encoder(x)                       # (batch, n_contracts, output_dim)
        aggregate = (attn_weights.unsqueeze(-1) * encoded).sum(dim=1)  # (batch, output_dim)
        quality = self.quality_head(aggregate).squeeze(-1)

        return aggregate, attn_weights, quality

    def aggregate_numpy(
        self,
        contract_features: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray, float]:
        """
        Convenience wrapper for inference on a single cluster (no batch dim).

        contract_features: (n_contracts, input_dim)
        Returns: (aggregate_vector, attention_weights, quality_score)
        """
        self.eval()
        with torch.no_grad():
            x = torch.tensor(contract_features, dtype=torch.float32).unsqueeze(0)
            agg, attn, qual = self.forward(x)
        return (
            agg.squeeze(0).numpy(),
            attn.squeeze(0).numpy(),
            float(qual.item()),
        )

    def save(self) -> str:
        path = os.path.join(ARTIFACTS_PATH, "cluster_aggregator.pt")
        os.makedirs(ARTIFACTS_PATH, exist_ok=True)
        # Export as TorchScript for portable serving
        example = torch.zeros(1, 3, CLUSTER_INPUT_DIM)
        scripted = torch.jit.trace(self, (example,))
        torch.jit.save(scripted, path)
        return path

    @classmethod
    def load(cls) -> "ClusterAggregator":
        path = os.path.join(ARTIFACTS_PATH, "cluster_aggregator.pt")
        if not os.path.exists(path):
            raise FileNotFoundError(f"No saved ClusterAggregator at {path}")
        scripted = torch.jit.load(path)
        # Wrap in Python class for the non-jit methods
        instance = cls()
        instance.load_state_dict(
            {k: v for k, v in scripted.named_parameters()}, strict=False
        )
        return instance

    # Per-contract feature names used as input_dim=20 subset
    CONTRACT_FEATURE_NAMES = [
        "volume_ratio_20d", "vol_oi_ratio", "log_premium_total",
        "otm_pct", "days_to_expiry", "dte_bucket", "is_call",
        "delta_abs", "gamma", "theta_per_day", "vega", "theta_vega_ratio",
        "ba_spread_pct", "iv_at_event", "iv_vs_hv_ratio",
        "hour_of_day", "is_morning", "is_afternoon",
        "iv_rank", "underlying_return_1d",
    ]
