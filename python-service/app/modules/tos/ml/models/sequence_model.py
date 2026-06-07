"""
Model 6 — Event Sequence Transformer.

Question: Do back-to-back unusual volume events on the same ticker form
          a coherent pattern that predicts a sustained move?

Architecture: Positional-encoded Transformer encoder over a 5-day event
              window (up to 20 events per ticker), pooled to a single vector.

Input:  (batch, seq_len, feature_dim) — chronological event features
Output: (batch, hidden_dim) — sequence-level embedding

The embedding feeds into a two-head output:
  - sequence_quality: P(sequence is informative) [0,1]
  - direction_logit:  P(net underlying move in aggregate implied direction)
"""
import math
import os

import numpy as np
import torch
import torch.nn as nn


ARTIFACTS_PATH = os.getenv("MODEL_ARTIFACTS_PATH", "/app/artifacts")
SEQ_INPUT_DIM  = 24   # flattened per-event: CONTRACT_FEATURES subset + time delta
MAX_SEQ_LEN    = 20   # cap at 20 events per ticker per 5-day window


class PositionalEncoding(nn.Module):
    def __init__(self, d_model: int, max_len: int = MAX_SEQ_LEN, dropout: float = 0.1):
        super().__init__()
        self.dropout = nn.Dropout(dropout)
        pe = torch.zeros(max_len, d_model)
        pos = torch.arange(0, max_len, dtype=torch.float).unsqueeze(1)
        div = torch.exp(
            torch.arange(0, d_model, 2, dtype=torch.float) * (-math.log(10000.0) / d_model)
        )
        pe[:, 0::2] = torch.sin(pos * div)
        pe[:, 1::2] = torch.cos(pos * div)
        self.register_buffer("pe", pe.unsqueeze(0))  # (1, max_len, d_model)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = x + self.pe[:, : x.size(1)]
        return self.dropout(x)


class EventSequenceTransformer(nn.Module):
    """
    Transformer encoder over chronological unusual volume events for a single ticker.

    Learns temporal patterns: escalating sweep size, cross-strike accumulation,
    days-to-expiry convergence, momentum in IV rank — things a per-event model
    cannot see.
    """

    def __init__(
        self,
        input_dim: int = SEQ_INPUT_DIM,
        d_model: int = 64,
        nhead: int = 4,
        num_layers: int = 2,
        dim_feedforward: int = 128,
        dropout: float = 0.1,
    ):
        super().__init__()
        self.input_proj = nn.Linear(input_dim, d_model)
        self.pos_enc = PositionalEncoding(d_model, dropout=dropout)
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model,
            nhead=nhead,
            dim_feedforward=dim_feedforward,
            dropout=dropout,
            batch_first=True,
        )
        self.transformer = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)
        # CLS-style token prepended for sequence-level readout
        self.cls_token = nn.Parameter(torch.randn(1, 1, d_model))
        # Output heads
        self.quality_head = nn.Sequential(
            nn.Linear(d_model, 32), nn.ReLU(), nn.Linear(32, 1), nn.Sigmoid()
        )
        self.direction_head = nn.Sequential(
            nn.Linear(d_model, 32), nn.ReLU(), nn.Linear(32, 1), nn.Sigmoid()
        )

    def forward(
        self,
        x: torch.Tensor,
        src_key_padding_mask: torch.Tensor | None = None,
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """
        Args:
            x:                     (batch, seq_len, input_dim)
            src_key_padding_mask:  (batch, seq_len+1) True for padded positions

        Returns:
            embedding:   (batch, d_model) — CLS token output
            quality:     (batch,) — P(sequence informative) in [0,1]
            direction:   (batch,) — P(net move in aggregate implied direction)
        """
        batch = x.size(0)
        x = self.input_proj(x)                         # (batch, seq_len, d_model)
        x = self.pos_enc(x)

        cls = self.cls_token.expand(batch, -1, -1)     # (batch, 1, d_model)
        x = torch.cat([cls, x], dim=1)                 # (batch, seq_len+1, d_model)

        out = self.transformer(x, src_key_padding_mask=src_key_padding_mask)
        embedding = out[:, 0]                          # CLS position

        quality   = self.quality_head(embedding).squeeze(-1)
        direction = self.direction_head(embedding).squeeze(-1)
        return embedding, quality, direction

    # ------------------------------------------------------------------
    # Numpy convenience wrapper for inference
    # ------------------------------------------------------------------

    def score_sequence(
        self,
        event_features: np.ndarray,
    ) -> dict:
        """
        Score a single event sequence (no batch dim).

        event_features: (seq_len, input_dim) — chronological, oldest first
        Returns: {"embedding": np.ndarray, "quality": float, "direction": float}
        """
        self.eval()
        seq_len = min(event_features.shape[0], MAX_SEQ_LEN)
        events = event_features[-seq_len:]             # most recent seq_len events
        with torch.no_grad():
            x = torch.tensor(events, dtype=torch.float32).unsqueeze(0)
            emb, qual, dirn = self.forward(x)
        return {
            "embedding": emb.squeeze(0).numpy(),
            "quality":   float(qual.item()),
            "direction": float(dirn.item()),
        }

    # ------------------------------------------------------------------
    # Persistence (TorchScript export)
    # ------------------------------------------------------------------

    def save(self) -> str:
        path = os.path.join(ARTIFACTS_PATH, "sequence_model.pt")
        os.makedirs(ARTIFACTS_PATH, exist_ok=True)
        example_x = torch.zeros(1, 5, SEQ_INPUT_DIM)
        scripted = torch.jit.trace(self, (example_x,), strict=False)
        torch.jit.save(scripted, path)
        return path

    @classmethod
    def load(cls) -> "EventSequenceTransformer":
        path = os.path.join(ARTIFACTS_PATH, "sequence_model.pt")
        if not os.path.exists(path):
            raise FileNotFoundError(f"No saved EventSequenceTransformer at {path}")
        # Load TorchScript for serving, or fall back to a fresh instance
        try:
            return torch.jit.load(path)
        except Exception:
            instance = cls()
            instance.load_state_dict(torch.load(path, weights_only=True))
            return instance

    # Feature names that compose SEQ_INPUT_DIM=24 per event slot
    EVENT_FEATURE_NAMES = [
        # Contract geometry (10)
        "volume_ratio_20d", "vol_oi_ratio", "log_premium_total",
        "otm_pct", "days_to_expiry", "is_call",
        "delta_abs", "gamma", "iv_at_event", "ba_spread_pct",
        # Underlying context at event time (10)
        "underlying_return_1d", "underlying_return_5d",
        "iv_rank", "iv_change_1d", "put_call_ratio",
        "spy_return_1d", "vix_level",
        "hour_of_day", "is_morning", "is_afternoon",
        # Temporal position features (4)
        "days_since_prev_event",      # 0 for the first event in the window
        "events_in_last_24h",         # count of same-ticker events in past day
        "same_strike_repeat",         # 1 if same strike fired within 48h
        "net_call_bias_window",       # rolling call fraction over the window
    ]
