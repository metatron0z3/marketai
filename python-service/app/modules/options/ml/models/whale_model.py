from .lgbm_model import LGBMOptionsModel

WHALE_FEATURE_COLS = [
    "cluster_premium_total",
    "cluster_size_max",
    "cluster_trade_count",
    "strike_concentration",
    "avg_dte",
    "otm_pct",
    "avg_delta",
    "premium_per_trade",
    "vol_oi_ratio",
    "iv_rank",
    "accumulation_days",
    "call_put_ratio",
]


class LGBMWhaleModel(LGBMOptionsModel):
    """LightGBM classifier for whale positioning signals (2-8 week horizon)."""
    pass
