"""
Research 1 — Granger Causality: Does unusual options volume predict price moves?

Tests whether lagged options flow metrics (put_call_ratio, net_premium, unusual_count)
Granger-cause 1-day and 5-day underlying returns for each ticker.

Output: DataFrame with p-values per ticker/feature/lag combination.
Use this to decide which features are worth including in the main models.

Usage:
    python -m app.modules.tos.ml.research.granger_causality
    python -m app.modules.tos.ml.research.granger_causality --symbol TSLA --max-lag 5
"""
import argparse
import logging

import numpy as np
import pandas as pd

from app.modules.tos.db.tos_db import get_tos_postgres, get_tos_questdb, tos_available

log = logging.getLogger(__name__)

CAUSE_FEATURES = [
    "net_call_premium",      # call premium - put premium on the day
    "unusual_event_count",   # n unusual volume events fired
    "put_call_ratio",
    "weighted_iv_change",    # IV-weighted change across events
    "sweep_count",           # aggressive sweep count
]


def load_daily_series(symbol: str, min_days: int = 60) -> pd.DataFrame | None:
    """
    Build a daily time series by joining TOS Postgres daily summary
    with QuestDB underlying prices.
    """
    if not tos_available():
        return None
    try:
        pg = get_tos_postgres()
        qdb = get_tos_questdb()

        # Daily flow aggregates from Postgres
        with pg.cursor() as cur:
            cur.execute("""
                SELECT
                    DATE(detected_at)                    AS date,
                    COUNT(*)                             AS unusual_event_count,
                    SUM(CASE WHEN is_call THEN premium_total ELSE 0 END) -
                    SUM(CASE WHEN NOT is_call THEN premium_total ELSE 0 END) AS net_call_premium,
                    AVG(CASE WHEN is_call THEN 1.0 ELSE 0.0 END)            AS call_ratio,
                    COUNT(CASE WHEN is_sweep THEN 1 END)                    AS sweep_count
                FROM signal_catalog
                WHERE symbol = %(sym)s
                GROUP BY 1
                ORDER BY 1
            """, {"sym": symbol})
            flow = pd.DataFrame(cur.fetchall(),
                                columns=["date", "unusual_event_count", "net_call_premium",
                                         "call_ratio", "sweep_count"])

        # Daily returns from QuestDB
        with qdb.cursor() as cur:
            cur.execute("""
                SELECT timestamp::date AS date,
                       (close - prev_close) / prev_close AS daily_return
                FROM (
                    SELECT timestamp,
                           close,
                           LAG(close) OVER (ORDER BY timestamp) AS prev_close
                    FROM   underlying_intraday_bars
                    WHERE  symbol = %(sym)s
                    SAMPLE BY 1d
                )
                WHERE prev_close IS NOT NULL
                ORDER BY date
            """, {"sym": symbol})
            prices = pd.DataFrame(cur.fetchall(), columns=["date", "daily_return"])

        pg.close()
        qdb.close()

        merged = flow.merge(prices, on="date", how="inner")
        merged["put_call_ratio"] = 1.0 / (merged["call_ratio"].replace(0, np.nan))
        merged["date"] = pd.to_datetime(merged["date"])
        merged = merged.sort_values("date").reset_index(drop=True)

        if len(merged) < min_days:
            log.warning("%s: only %d days, need %d", symbol, len(merged), min_days)
            return None
        return merged
    except Exception as e:
        log.warning("load_daily_series failed for %s: %s", symbol, e)
        return None


def run_granger_tests(
    symbol: str,
    max_lag: int = 5,
    significance: float = 0.05,
) -> pd.DataFrame:
    """
    Run Granger causality tests: do flow features Granger-cause daily_return?

    Returns DataFrame with columns:
        symbol, feature, lag, f_stat, p_value, significant
    """
    from statsmodels.tsa.stattools import grangercausalitytests

    df = load_daily_series(symbol)
    if df is None:
        return pd.DataFrame()

    records = []
    target = "daily_return"

    for feat in CAUSE_FEATURES:
        if feat not in df.columns:
            continue
        series = df[[target, feat]].dropna()
        if len(series) < 30:
            continue
        try:
            results = grangercausalitytests(series, maxlag=max_lag, verbose=False)
            for lag, res in results.items():
                f_stat = res[0]["ssr_ftest"][0]
                p_val  = res[0]["ssr_ftest"][1]
                records.append({
                    "symbol": symbol, "feature": feat, "lag": lag,
                    "f_stat": round(f_stat, 4), "p_value": round(p_val, 4),
                    "significant": p_val < significance,
                })
        except Exception as e:
            log.warning("Granger test failed %s/%s: %s", symbol, feat, e)

    return pd.DataFrame(records)


def run_all_symbols(symbols: list[str], max_lag: int = 5) -> pd.DataFrame:
    frames = [run_granger_tests(sym, max_lag) for sym in symbols]
    result = pd.concat([f for f in frames if not f.empty], ignore_index=True)
    if result.empty:
        return result
    return result.sort_values(["symbol", "p_value"])


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default=None)
    parser.add_argument("--max-lag", type=int, default=5)
    args = parser.parse_args()

    symbols = [args.symbol] if args.symbol else [
        "TSLA", "NVDA", "SPY", "QQQ", "AAPL", "AMD",
        "META", "AMZN", "MSFT", "GLD", "TLT",
    ]
    results = run_all_symbols(symbols, max_lag=args.max_lag)
    if results.empty:
        print("No results (TOS database unavailable or insufficient data).")
    else:
        sig = results[results["significant"]]
        print(f"\nSignificant Granger causality ({len(sig)} pairs at p<0.05):\n")
        print(sig.to_string(index=False))
        out = "granger_causality_results.csv"
        results.to_csv(out, index=False)
        print(f"\nFull results saved to {out}")


if __name__ == "__main__":
    main()
