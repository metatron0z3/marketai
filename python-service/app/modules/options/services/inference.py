import os
from functools import lru_cache
from datetime import datetime, timezone

from app.core.db import get_db_connection

ARTIFACTS_PATH = os.getenv("MODEL_ARTIFACTS_PATH", "/app/artifacts")
FEATURE_COLS = [
    "rvol", "vol_oi_ratio", "premium_flow", "sweep_intensity",
    "aggressor_ratio", "delta_exposure", "iv_rank", "days_to_exp",
]


@lru_cache(maxsize=1)
def _load_model():
    """Load TorchScript model once and cache it."""
    import torch
    model_path = os.path.join(ARTIFACTS_PATH, "options_model.pt")
    if not os.path.exists(model_path):
        return None
    return torch.jit.load(model_path)


@lru_cache(maxsize=1)
def _load_normalizer():
    """Load fitted SequenceNormalizer once and cache it."""
    import pickle
    norm_path = os.path.join(ARTIFACTS_PATH, "normalizer.pkl")
    if not os.path.exists(norm_path):
        return None
    with open(norm_path, "rb") as f:
        return pickle.load(f)


def predict(contract: dict) -> dict:
    """
    Run inference on a single contract snapshot.
    Returns signal_score in [0, 1] (probability of >2% move within 24h).
    Falls back to rule-based score if no model is loaded.
    """
    features = [float(contract.get(col, 0) or 0) for col in FEATURE_COLS]

    model = _load_model()
    normalizer = _load_normalizer()

    if model is not None and normalizer is not None:
        import torch
        import numpy as np
        x = normalizer.transform([features])
        tensor = torch.tensor(x, dtype=torch.float32)
        with torch.no_grad():
            score = float(torch.sigmoid(model(tensor)).squeeze())
    else:
        # Rule-based fallback: weighted heuristic from key signals
        rvol = float(contract.get("rvol", 0) or 0)
        sweep = float(contract.get("sweep_intensity", 0) or 0)
        aggressor = float(contract.get("aggressor_ratio", 0) or 0)
        score = min((rvol * 0.4 + sweep * 0.3 + aggressor * 0.3) / 10.0, 1.0)

    return {
        "signal_score": round(score, 4),
        "model_loaded": model is not None,
        "scored_at": datetime.now(timezone.utc).isoformat(),
    }


def top_signals(n: int = 20, lookback_minutes: int = 30) -> list[dict]:
    """Return the top-N signals from options_features over the last lookback_minutes."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        f"""
        SELECT ts_event, symbol, strike, expiration, put_call,
               rvol, vol_oi_ratio, premium_flow, sweep_intensity,
               aggressor_ratio, delta_exposure, iv_rank, days_to_exp
        FROM options_features
        WHERE ts_event >= dateadd('m', -{lookback_minutes}, now())
        ORDER BY ts_event DESC
        LIMIT {n * 5}
        """
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()

    cols = [
        "ts_event", "symbol", "strike", "expiration", "put_call",
        "rvol", "vol_oi_ratio", "premium_flow", "sweep_intensity",
        "aggressor_ratio", "delta_exposure", "iv_rank", "days_to_exp",
    ]
    results = []
    for row in rows:
        contract = dict(zip(cols, row))
        scored = predict(contract)
        results.append({**contract, **scored})

    results.sort(key=lambda x: x["signal_score"], reverse=True)
    return results[:n]
