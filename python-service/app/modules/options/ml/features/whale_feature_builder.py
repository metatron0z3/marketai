import numpy as np
import pandas as pd

from app.core.db import get_db_connection
from app.modules.options.ml.models.whale_model import WHALE_FEATURE_COLS


def load_labeled_whale_features(symbol: str | None = None) -> tuple[np.ndarray, np.ndarray]:
    """
    Pull labeled rows from whale_features.
    Returns (X, y) — only rows where label_4w is not null.
    Normalizer is fit externally on the training split only.
    """
    conn = get_db_connection()
    cur = conn.cursor()

    where = "WHERE label_4w IS NOT NULL"
    params: list = []
    if symbol:
        where += " AND symbol = %s"
        params.append(symbol)

    cur.execute(
        f"""
        SELECT {", ".join(WHALE_FEATURE_COLS)}, label_4w
        FROM whale_features
        {where}
        ORDER BY ts_event
        """,
        params or None,
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()

    if not rows:
        return np.empty((0, len(WHALE_FEATURE_COLS))), np.empty(0)

    df = pd.DataFrame(rows, columns=WHALE_FEATURE_COLS + ["label_4w"])
    df = df.fillna(0)
    X = df[WHALE_FEATURE_COLS].values.astype(np.float32)
    y = df["label_4w"].values.astype(np.int32)
    return X, y
