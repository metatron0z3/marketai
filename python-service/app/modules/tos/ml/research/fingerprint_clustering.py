"""
Research 2 — Options Flow Fingerprinting.

Cluster historical unusual volume events to find recurring "fingerprint" patterns:
  - The 3-week accumulation cluster (same strike, weekly buys)
  - The single-day sweep (aggressive, all at once)
  - The earnings hedge (long DTE, high gamma, defensive skew)
  - The synthetic replacement (deep ITM call replacing stock position)
  - The speculative lottery ticket (far OTM, 0-2 DTE, huge volume)

Uses HDBSCAN (density-based, no need to specify n_clusters) on a feature
embedding from the contract geometry features.

Output: cluster labels + per-cluster summary statistics.
"""
import logging

import numpy as np
import pandas as pd

from app.modules.tos.db.tos_db import get_tos_postgres, tos_available

log = logging.getLogger(__name__)

FINGERPRINT_FEATURES = [
    "volume_ratio_20d",
    "vol_oi_ratio",
    "otm_pct",
    "days_to_expiry",
    "is_call",
    "delta_abs",
    "gamma",
    "ba_spread_pct",
    "iv_at_event",
    "log_premium_total",
    "is_sweep",
    "hour_of_day",
]

FINGERPRINT_NAMES = {
    # Assigned after visual inspection of cluster centroids
    # Placeholder labels — update after running on real data
    0: "single_day_sweep",
    1: "accumulation_pattern",
    2: "earnings_hedge",
    3: "otm_lottery",
    4: "synthetic_replacement",
}


def load_event_features(symbol: str | None = None, min_rows: int = 200) -> pd.DataFrame | None:
    if not tos_available():
        return None
    try:
        pg = get_tos_postgres()
        query = """
            SELECT signal_id, symbol,
                   volume_ratio_20d, vol_oi_ratio, otm_pct,
                   days_to_expiry, is_call, delta_abs, gamma,
                   ba_spread_pct, iv_at_event, log_premium_total,
                   is_sweep, hour_of_day,
                   -- outcome (if available)
                   underlying_return_5d_fwd,
                   direction_correct_5d
            FROM   signal_catalog
            WHERE  %(sym_filter)s
            ORDER  BY detected_at DESC
        """
        sym_filter = "symbol = %(symbol)s" if symbol else "TRUE"
        with pg.cursor() as cur:
            cur.execute(query.replace("%(sym_filter)s", sym_filter),
                        {"symbol": symbol} if symbol else {})
            rows = cur.fetchall()
        pg.close()

        cols = ["signal_id", "symbol", "volume_ratio_20d", "vol_oi_ratio",
                "otm_pct", "days_to_expiry", "is_call", "delta_abs", "gamma",
                "ba_spread_pct", "iv_at_event", "log_premium_total", "is_sweep",
                "hour_of_day", "underlying_return_5d_fwd", "direction_correct_5d"]
        df = pd.DataFrame(rows, columns=cols)
        if len(df) < min_rows:
            log.warning("Only %d rows for fingerprinting (need %d)", len(df), min_rows)
            return None
        return df
    except Exception as e:
        log.warning("load_event_features failed: %s", e)
        return None


def run_fingerprint_clustering(
    symbol: str | None = None,
    min_cluster_size: int = 10,
) -> pd.DataFrame:
    """
    Run HDBSCAN on event features and return the labeled dataset.

    Returns: DataFrame with all original columns + 'cluster_id' + 'cluster_name'
    """
    import hdbscan
    from sklearn.preprocessing import StandardScaler

    df = load_event_features(symbol)
    if df is None:
        return pd.DataFrame()

    feature_cols = [f for f in FINGERPRINT_FEATURES if f in df.columns]
    X = df[feature_cols].fillna(0).values
    X_scaled = StandardScaler().fit_transform(X)

    clusterer = hdbscan.HDBSCAN(
        min_cluster_size=min_cluster_size,
        min_samples=5,
        metric="euclidean",
        cluster_selection_method="eom",
    )
    labels = clusterer.fit_predict(X_scaled)

    df = df.copy()
    df["cluster_id"]   = labels
    df["cluster_name"] = df["cluster_id"].map(FINGERPRINT_NAMES).fillna("noise")
    return df


def cluster_outcome_summary(df: pd.DataFrame) -> pd.DataFrame:
    """
    For each cluster, compute outcome statistics (requires labeled data).
    """
    if df.empty or "cluster_id" not in df.columns:
        return pd.DataFrame()

    labeled = df[df["underlying_return_5d_fwd"].notna()].copy()
    if labeled.empty:
        return pd.DataFrame()

    summary = labeled.groupby("cluster_name").agg(
        n                      = ("signal_id", "count"),
        pct_direction_correct  = ("direction_correct_5d", "mean"),
        mean_return_5d         = ("underlying_return_5d_fwd", "mean"),
        median_return_5d       = ("underlying_return_5d_fwd", "median"),
        std_return_5d          = ("underlying_return_5d_fwd", "std"),
    ).round(4).reset_index()
    return summary.sort_values("pct_direction_correct", ascending=False)


def main():
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default=None)
    parser.add_argument("--min-cluster-size", type=int, default=10)
    args = parser.parse_args()

    df = run_fingerprint_clustering(args.symbol, args.min_cluster_size)
    if df.empty:
        print("No data available.")
        return

    print(f"\nCluster distribution:\n{df['cluster_name'].value_counts()}\n")
    summary = cluster_outcome_summary(df)
    if not summary.empty:
        print("Outcome by cluster:\n")
        print(summary.to_string(index=False))
    df.to_csv("fingerprint_clusters.csv", index=False)
    print("\nFull dataset saved to fingerprint_clusters.csv")


if __name__ == "__main__":
    main()
