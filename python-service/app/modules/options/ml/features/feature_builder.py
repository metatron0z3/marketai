import numpy as np
import pandas as pd

from app.core.db import get_db_connection
from app.modules.options.ml.models.base_model import BaseFinancialModel

FEATURE_COLS = BaseFinancialModel.FEATURE_COLS


def load_labeled_features(symbol: str | None = None) -> tuple[np.ndarray, np.ndarray]:
    """
    Pull labeled rows from options_features.
    Returns (X, y) — only rows where label_24h is not null.
    Normalizer is fit externally on the training split only.
    """
    conn = get_db_connection()
    cur = conn.cursor()

    where = "WHERE label_24h IS NOT NULL"
    params = []
    if symbol:
        where += " AND symbol = %s"
        params.append(symbol)

    cur.execute(
        f"""
        SELECT {", ".join(FEATURE_COLS)}, label_24h
        FROM options_features
        {where}
        ORDER BY ts_event
        """,
        params or None,
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()

    if not rows:
        return np.empty((0, len(FEATURE_COLS))), np.empty(0)

    df = pd.DataFrame(rows, columns=FEATURE_COLS + ["label_24h"])
    df = df.fillna(0)
    X = df[FEATURE_COLS].values.astype(np.float32)
    y = df["label_24h"].values.astype(np.int32)
    return X, y
