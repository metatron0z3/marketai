import os
from functools import lru_cache
from datetime import datetime, timezone

from app.core.db import get_db_connection
from app.modules.options.ml.models.base_model import BaseFinancialModel

ARTIFACTS_PATH = os.getenv("MODEL_ARTIFACTS_PATH", "/app/artifacts")
FEATURE_COLS = BaseFinancialModel.FEATURE_COLS


@lru_cache(maxsize=1)
def _load_model():
    import torch
    path = os.path.join(ARTIFACTS_PATH, "options_model.pt")
    if not os.path.exists(path):
        return None
    return torch.jit.load(path)


@lru_cache(maxsize=1)
def _load_normalizer():
    import pickle
    # Filename matches what model_registry.save_normalizer("options_model") produces
    path = os.path.join(ARTIFACTS_PATH, "options_model_normalizer.pkl")
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        return pickle.load(f)


def predict(contract: dict) -> dict:
    features = [float(contract.get(col, 0) or 0) for col in FEATURE_COLS]

    model = _load_model()
    normalizer = _load_normalizer()
    model_active = model is not None and normalizer is not None

    if model_active:
        import torch
        x = normalizer.transform([features])
        tensor = torch.tensor(x, dtype=torch.float32)
        with torch.no_grad():
            score = float(torch.sigmoid(model(tensor)).squeeze())
    else:
        rvol = float(contract.get("rvol", 0) or 0)
        sweep = float(contract.get("sweep_intensity", 0) or 0)
        aggressor = float(contract.get("aggressor_ratio", 0) or 0)
        score = min((rvol * 0.4 + sweep * 0.3 + aggressor * 0.3) / 10.0, 1.0)

    return {
        "signal_score": round(score, 4),
        "model_loaded": model_active,
        "scored_at": datetime.now(timezone.utc).isoformat(),
    }


def top_signals(n: int = 20, lookback_minutes: int = 30) -> list[dict]:
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        f"""
        SELECT ts_event, symbol, strike, expiration, put_call,
               {", ".join(FEATURE_COLS)}
        FROM options_features
        WHERE ts_event >= dateadd('m', -{lookback_minutes}, now())
        ORDER BY ts_event DESC
        LIMIT {n * 5}
        """
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()

    col_names = ["ts_event", "symbol", "strike", "expiration", "put_call"] + list(FEATURE_COLS)
    results = []
    for row in rows:
        contract = dict(zip(col_names, row))
        results.append({**contract, **predict(contract)})

    results.sort(key=lambda x: x["signal_score"], reverse=True)
    return results[:n]
