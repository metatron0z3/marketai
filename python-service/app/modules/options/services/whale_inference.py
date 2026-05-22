import os
import pickle
from datetime import datetime, timezone
from functools import lru_cache

from app.core.db import get_db_connection
from app.modules.options.ml.models.whale_model import WHALE_FEATURE_COLS

ARTIFACTS_PATH = os.getenv("MODEL_ARTIFACTS_PATH", "/app/artifacts")


@lru_cache(maxsize=1)
def _load_model():
    path = os.path.join(ARTIFACTS_PATH, "whale_model.pkl")
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        return pickle.load(f)


@lru_cache(maxsize=1)
def _load_normalizer():
    path = os.path.join(ARTIFACTS_PATH, "whale_model_normalizer.pkl")
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        return pickle.load(f)


def whale_predict(snapshot: dict) -> dict:
    features = [float(snapshot.get(col, 0) or 0) for col in WHALE_FEATURE_COLS]

    model = _load_model()
    normalizer = _load_normalizer()
    model_active = model is not None and normalizer is not None

    if model_active:
        x = normalizer.transform([features])
        score = float(model.predict_proba(x)[0])
    else:
        # Rule-based fallback: weight cluster size, accumulation depth, and strike focus
        vals = dict(zip(WHALE_FEATURE_COLS, features))
        raw = (
            min(vals["cluster_premium_total"] / 1_000_000, 1.0) * 0.5
            + min(vals["accumulation_days"] / 5, 1.0) * 0.3
            + float(vals["strike_concentration"]) * 0.2
        )
        score = min(raw, 1.0)

    return {
        "whale_signal_score": round(score, 4),
        "model_loaded": model_active,
        "scored_at": datetime.now(timezone.utc).isoformat(),
    }


def whale_top_signals(n: int = 20, lookback_days: int = 5) -> list[dict]:
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        f"""
        SELECT ts_event, symbol, strike, expiration, put_call,
               {", ".join(WHALE_FEATURE_COLS)}
        FROM whale_features
        WHERE ts_event >= dateadd('d', -{lookback_days}, now())
        ORDER BY ts_event DESC
        LIMIT {n * 5}
        """
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()

    col_names = ["ts_event", "symbol", "strike", "expiration", "put_call"] + list(WHALE_FEATURE_COLS)
    results = []
    for row in rows:
        snapshot = dict(zip(col_names, row))
        results.append({**snapshot, **whale_predict(snapshot)})

    results.sort(key=lambda x: x["whale_signal_score"], reverse=True)
    return results[:n]
