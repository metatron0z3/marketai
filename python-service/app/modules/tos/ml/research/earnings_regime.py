"""
Research 5 — Earnings Regime Analysis.

Options flow around earnings events has fundamentally different characteristics:
  - IV crush after announcement makes most long options unprofitable regardless of direction
  - Smart money often positions 2–4 weeks BEFORE earnings via synthetic positions
  - Unusual volume in long-DTE options 2+ weeks before earnings is more bullish than
    unusual short-DTE volume 1–2 days before (which is mostly retail speculation)
  - The "earnings overwrite" pattern: large call sell + stock = covered call gamma harvest

This research module:
  1. Loads earnings calendar from TOS Postgres
  2. Segments all unusual volume events into pre/post/control periods
  3. Computes signal quality statistics for each segment
  4. Identifies pre-earnings positioning patterns that outperform
"""
import logging
from dataclasses import dataclass

import pandas as pd

from app.modules.tos.db.tos_db import get_tos_postgres, tos_available

log = logging.getLogger(__name__)


@dataclass
class EarningsSegmentStats:
    symbol: str
    period: str            # "pre_30d", "pre_14d", "pre_7d", "pre_2d", "post_3d", "control"
    n_events: int
    pct_calls: float
    avg_dte: float
    pct_direction_correct: float
    avg_return_5d: float
    avg_conviction: float  # if scored


def load_earnings_calendar(symbol: str | None = None) -> pd.DataFrame | None:
    if not tos_available():
        return None
    try:
        pg = get_tos_postgres()
        query = "SELECT symbol, earnings_date, confirmed FROM earnings_calendar"
        params = {}
        if symbol:
            query += " WHERE symbol = %(sym)s"
            params["sym"] = symbol
        with pg.cursor() as cur:
            cur.execute(query, params)
            rows = cur.fetchall()
        pg.close()
        return pd.DataFrame(rows, columns=["symbol", "earnings_date", "confirmed"])
    except Exception as e:
        log.warning("load_earnings_calendar failed: %s", e)
        return None


def load_signal_data(symbol: str | None = None) -> pd.DataFrame | None:
    if not tos_available():
        return None
    try:
        pg = get_tos_postgres()
        query = """
            SELECT sc.signal_id, sc.symbol, sc.detected_at,
                   sc.is_call, sc.days_to_expiry, sc.premium_total,
                   sc.direction_correct_5d, sc.underlying_return_5d_fwd,
                   cs.conviction_score
            FROM   signal_catalog sc
            LEFT JOIN conviction_scores cs ON sc.signal_id = cs.signal_id
        """
        params = {}
        if symbol:
            query += " WHERE sc.symbol = %(sym)s"
            params["sym"] = symbol
        with pg.cursor() as cur:
            cur.execute(query, params)
            rows = cur.fetchall()
        pg.close()
        cols = ["signal_id", "symbol", "detected_at", "is_call", "days_to_expiry",
                "premium_total", "direction_correct_5d", "underlying_return_5d_fwd",
                "conviction_score"]
        return pd.DataFrame(rows, columns=cols)
    except Exception as e:
        log.warning("load_signal_data failed: %s", e)
        return None


def _classify_period(row: pd.Series, earnings_df: pd.DataFrame) -> str:
    """Classify a signal relative to the nearest earnings event for its ticker."""
    sym_earnings = earnings_df[earnings_df["symbol"] == row["symbol"]]["earnings_date"]
    if sym_earnings.empty:
        return "control"

    detected = pd.Timestamp(row["detected_at"])
    diffs = (pd.to_datetime(sym_earnings) - detected).dt.days
    nearest = diffs.iloc[diffs.abs().argmin()]

    if 14 <= nearest <= 30:
        return "pre_30d"
    elif 7 <= nearest < 14:
        return "pre_14d"
    elif 2 <= nearest < 7:
        return "pre_7d"
    elif 0 <= nearest < 2:
        return "pre_2d"
    elif -3 <= nearest < 0:
        return "post_3d"
    else:
        return "control"


def run_earnings_analysis(symbol: str | None = None) -> list[EarningsSegmentStats]:
    earnings = load_earnings_calendar(symbol)
    signals  = load_signal_data(symbol)

    if earnings is None or signals is None or earnings.empty or signals.empty:
        log.warning("Insufficient data for earnings regime analysis")
        return []

    signals = signals.copy()
    signals["period"] = signals.apply(_classify_period, axis=1, earnings_df=earnings)

    results = []
    for (sym, period), grp in signals.groupby(["symbol", "period"]):
        labeled = grp[grp["direction_correct_5d"].notna()]
        results.append(EarningsSegmentStats(
            symbol=str(sym),
            period=str(period),
            n_events=len(grp),
            pct_calls=float(grp["is_call"].mean()),
            avg_dte=float(grp["days_to_expiry"].mean()),
            pct_direction_correct=float(labeled["direction_correct_5d"].mean())
                if not labeled.empty else float("nan"),
            avg_return_5d=float(labeled["underlying_return_5d_fwd"].mean())
                if not labeled.empty else float("nan"),
            avg_conviction=float(grp["conviction_score"].mean())
                if grp["conviction_score"].notna().any() else float("nan"),
        ))

    return results


def results_to_dataframe(results: list[EarningsSegmentStats]) -> pd.DataFrame:
    return pd.DataFrame([
        {
            "symbol": r.symbol, "period": r.period, "n_events": r.n_events,
            "pct_calls": round(r.pct_calls, 3), "avg_dte": round(r.avg_dte, 1),
            "pct_direction_correct": round(r.pct_direction_correct, 3),
            "avg_return_5d": round(r.avg_return_5d, 4),
            "avg_conviction": round(r.avg_conviction, 3),
        }
        for r in results
    ])


def main():
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default=None)
    args = parser.parse_args()

    results = run_earnings_analysis(args.symbol)
    if not results:
        print("No data available.")
        return

    df = results_to_dataframe(results)
    df = df.sort_values(["symbol", "period"])
    print(df.to_string(index=False))
    df.to_csv("earnings_regime_results.csv", index=False)
    print("\nSaved to earnings_regime_results.csv")


if __name__ == "__main__":
    main()
