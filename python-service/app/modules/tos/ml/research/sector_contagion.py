"""
Research 3 — Sector Contagion: Does an unusual flow event on ticker A
predict unusual flow (or price movement) on related tickers B, C?

Example:
  - NVDA sweep fires → does AMD also see unusual activity within 24h?
  - SPY put sweep → does QQQ put/call ratio spike?
  - TSLA call accumulation → does it predict TSLA itself OR sector ETF?

This is useful for:
  1. Building cross-ticker conviction boosters
  2. Constructing synthetic "sector flow pressure" features
  3. Identifying when a smart-money position is being hedged in an index

Method: event-based cross-correlation with a 0–48h lead-lag window.
"""
import logging
from itertools import combinations

import numpy as np
import pandas as pd

from app.modules.tos.db.tos_db import get_tos_postgres, tos_available

log = logging.getLogger(__name__)

# Sector groupings for contagion analysis
SECTOR_GROUPS = {
    "semis":  ["NVDA", "AMD"],
    "tech":   ["AAPL", "MSFT", "AMZN", "META"],
    "macro":  ["SPY", "QQQ", "GLD", "TLT"],
    "ev":     ["TSLA"],
}

# All watchlist symbols
ALL_SYMBOLS = ["TSLA", "NVDA", "SPY", "QQQ", "AAPL", "AMD",
               "META", "AMZN", "MSFT", "GLD", "TLT"]


def load_event_timestamps(symbols: list[str]) -> pd.DataFrame | None:
    """Load detected_at, symbol, is_call, premium_total for all events."""
    if not tos_available():
        return None
    try:
        pg = get_tos_postgres()
        placeholders = ", ".join(["%s"] * len(symbols))
        with pg.cursor() as cur:
            cur.execute(f"""
                SELECT detected_at, symbol, is_call,
                       premium_total, volume_ratio_20d,
                       underlying_return_1d_fwd
                FROM   signal_catalog
                WHERE  symbol IN ({placeholders})
                ORDER  BY detected_at
            """, symbols)
            rows = cur.fetchall()
        pg.close()
        return pd.DataFrame(rows, columns=[
            "detected_at", "symbol", "is_call",
            "premium_total", "volume_ratio_20d", "underlying_return_1d_fwd"
        ])
    except Exception as e:
        log.warning("load_event_timestamps failed: %s", e)
        return None


def compute_cross_correlation(
    df: pd.DataFrame,
    source: str,
    target: str,
    max_lag_hours: int = 48,
    bin_hours: int = 4,
) -> pd.DataFrame:
    """
    For each source event, count target events within [0, lag_h] hours after.
    Bins by lag_h intervals and computes correlation with source event quality.
    """
    src = df[df["symbol"] == source].copy()
    tgt = df[df["symbol"] == target].copy()

    if src.empty or tgt.empty:
        return pd.DataFrame()

    src["detected_at"] = pd.to_datetime(src["detected_at"])
    tgt["detected_at"] = pd.to_datetime(tgt["detected_at"])

    records = []
    lags = range(0, max_lag_hours + 1, bin_hours)

    for lag_h in lags:
        src_event_count = []
        tgt_event_count = []
        for _, row in src.iterrows():
            t0 = row["detected_at"]
            t1 = t0 + pd.Timedelta(hours=lag_h)
            t_start = t0 if lag_h > 0 else t0 - pd.Timedelta(hours=bin_hours)
            count = ((tgt["detected_at"] >= t_start) &
                     (tgt["detected_at"] <= t1)).sum()
            tgt_event_count.append(count)
            src_event_count.append(row["volume_ratio_20d"])

        if len(src_event_count) < 10:
            continue

        corr = float(np.corrcoef(src_event_count, tgt_event_count)[0, 1])
        records.append({
            "source": source, "target": target,
            "lag_hours": lag_h, "correlation": round(corr, 4),
            "n_source_events": len(src),
        })

    return pd.DataFrame(records)


def run_sector_contagion(max_lag_hours: int = 48) -> pd.DataFrame:
    """Run cross-correlation for all pairs within the same sector group."""
    df = load_event_timestamps(ALL_SYMBOLS)
    if df is None:
        return pd.DataFrame()

    frames = []
    for sector, symbols in SECTOR_GROUPS.items():
        if len(symbols) < 2:
            continue
        for src, tgt in combinations(symbols, 2):
            cc = compute_cross_correlation(df, src, tgt, max_lag_hours)
            if not cc.empty:
                cc["sector"] = sector
                frames.append(cc)
            cc2 = compute_cross_correlation(df, tgt, src, max_lag_hours)
            if not cc2.empty:
                cc2["sector"] = sector
                frames.append(cc2)

    # Also test all tickers → SPY/QQQ (macro impact)
    for sym in ALL_SYMBOLS:
        if sym in ("SPY", "QQQ"):
            continue
        for macro in ("SPY", "QQQ"):
            cc = compute_cross_correlation(df, sym, macro, max_lag_hours)
            if not cc.empty:
                cc["sector"] = "macro_impact"
                frames.append(cc)

    if not frames:
        return pd.DataFrame()

    return pd.concat(frames, ignore_index=True).sort_values(
        ["source", "target", "lag_hours"]
    )


def main():
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-lag-hours", type=int, default=48)
    args = parser.parse_args()

    results = run_sector_contagion(args.max_lag_hours)
    if results.empty:
        print("No data.")
        return

    strong = results[results["correlation"].abs() > 0.15]
    print(f"\nStrong cross-ticker correlations (|r| > 0.15): {len(strong)}\n")
    print(strong.to_string(index=False))
    results.to_csv("sector_contagion_results.csv", index=False)
    print("\nFull results saved to sector_contagion_results.csv")


if __name__ == "__main__":
    main()
