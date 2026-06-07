"""
Research 4 — Gamma Squeeze Detector.

A gamma squeeze occurs when market makers are short large amounts of near-strike
call options. As the stock rises, they must buy increasing amounts of shares to
stay delta-neutral, accelerating the move.

Detection heuristics:
  1. Large near-strike call volume (OTM ≤ 5%) relative to open interest
  2. Dealer gamma exposure (GEX) < 0 at the current price level
  3. IV rising with price (instead of falling — indicates demand-driven move)
  4. Put/call OI skew collapsing toward 1.0
  5. Multiple strikes with vol_oi_ratio > 1.5 within 2% of spot

Outputs:
  - Per-ticker gamma squeeze probability score [0, 1]
  - Estimated GEX estimate from available data
  - Alert if conditions cross threshold
"""
import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

from app.modules.tos.db.tos_db import get_tos_postgres, get_tos_questdb, tos_available

log = logging.getLogger(__name__)

SQUEEZE_THRESHOLD = 0.65


@dataclass
class SqueezeSignal:
    symbol: str
    score: float
    gex_estimate: float | None
    near_strike_call_vol_ratio: float
    oi_skew: float
    iv_rising_with_price: bool
    multi_strike_vol_pressure: int   # count of strikes with vol_oi > 1.5
    alert: bool

    def to_dict(self) -> dict:
        return {
            "symbol":                      self.symbol,
            "score":                       round(self.score, 4),
            "gex_estimate":                self.gex_estimate,
            "near_strike_call_vol_ratio":  round(self.near_strike_call_vol_ratio, 3),
            "oi_skew":                     round(self.oi_skew, 3),
            "iv_rising_with_price":        self.iv_rising_with_price,
            "multi_strike_vol_pressure":   self.multi_strike_vol_pressure,
            "alert":                       self.alert,
        }


def _compute_gex(chain_df: pd.DataFrame, spot: float) -> float:
    """
    Rough GEX estimate:
        GEX = Σ (gamma × OI × 100) for calls − Σ (gamma × OI × 100) for puts
    Positive GEX = dealers are long gamma (stabilizing).
    Negative GEX = dealers are short gamma (amplifying).
    """
    call_gex = (chain_df[chain_df["is_call"]]["gamma"] *
                chain_df[chain_df["is_call"]]["open_interest"] * 100).sum()
    put_gex  = (chain_df[~chain_df["is_call"]]["gamma"] *
                chain_df[~chain_df["is_call"]]["open_interest"] * 100).sum()
    return float(call_gex - put_gex)


def analyze_symbol(symbol: str) -> SqueezeSignal | None:
    if not tos_available():
        return None

    try:
        pg  = get_tos_postgres()
        qdb = get_tos_questdb()

        # Recent options chain snapshot
        with pg.cursor() as cur:
            cur.execute("""
                SELECT is_call, strike, open_interest, volume,
                       delta, gamma, iv, underlying_price
                FROM   options_chain_snapshots
                WHERE  symbol = %(sym)s
                ORDER  BY snapshot_time DESC
                LIMIT  500
            """, {"sym": symbol})
            chain_rows = cur.fetchall()

        if not chain_rows:
            pg.close(); qdb.close()
            return None

        chain = pd.DataFrame(chain_rows, columns=[
            "is_call", "strike", "open_interest", "volume",
            "delta", "gamma", "iv", "underlying_price"
        ])
        spot = float(chain["underlying_price"].iloc[0])

        # Recent unusual volume events
        with pg.cursor() as cur:
            cur.execute("""
                SELECT is_call, strike, volume_ratio_20d, vol_oi_ratio, iv_at_event
                FROM   signal_catalog
                WHERE  symbol = %(sym)s
                  AND  detected_at > NOW() - INTERVAL '1 day'
            """, {"sym": symbol})
            recent_events = cur.fetchall()

        # Recent price and IV trend from QuestDB
        with qdb.cursor() as cur:
            cur.execute("""
                SELECT close, iv_atm
                FROM   iv_surface_snapshots
                WHERE  symbol = %(sym)s
                ORDER  BY snapshot_time DESC
                LIMIT  5
            """, {"sym": symbol})
            iv_price_rows = cur.fetchall()

        pg.close(); qdb.close()

    except Exception as e:
        log.warning("analyze_symbol failed for %s: %s", symbol, e)
        return None

    # --- Heuristic scoring ---
    near_threshold = spot * 0.05
    near_calls = chain[
        chain["is_call"] &
        (chain["strike"] >= spot - near_threshold) &
        (chain["strike"] <= spot + near_threshold)
    ]
    far_calls = chain[chain["is_call"] & (chain["strike"] > spot + near_threshold)]

    near_vol = float(near_calls["volume"].sum())
    far_vol  = float(far_calls["volume"].sum())
    near_call_vol_ratio = near_vol / (far_vol + 1e-8)

    total_call_oi = float(chain[chain["is_call"]]["open_interest"].sum())
    total_put_oi  = float(chain[~chain["is_call"]]["open_interest"].sum())
    oi_skew = total_put_oi / (total_call_oi + 1e-8)

    gex = _compute_gex(chain, spot) if chain["gamma"].notna().any() else None

    # IV rising with price?
    iv_rising_with_price = False
    if len(iv_price_rows) >= 3:
        closes = [r[0] for r in iv_price_rows]
        ivs    = [r[1] for r in iv_price_rows if r[1] is not None]
        if len(ivs) >= 3:
            price_up = closes[0] > closes[-1]
            iv_up    = ivs[0] > ivs[-1]
            iv_rising_with_price = price_up and iv_up

    # Multi-strike pressure from recent events
    multi_strike_events = [
        r for r in recent_events
        if r[0]  # is_call
        and (r[3] or 0) > 1.5   # vol_oi_ratio
        and abs((r[1] or spot) - spot) / spot < 0.02
    ]
    multi_strike_count = len(multi_strike_events)

    # Composite score
    score_components = [
        min(near_call_vol_ratio / 5.0, 1.0),            # near-strike call vol
        max(0, 1.0 - oi_skew) if oi_skew < 2 else 0.3, # skew collapsing
        1.0 if iv_rising_with_price else 0.0,
        min(multi_strike_count / 5.0, 1.0),
        (1.0 if gex is not None and gex < 0 else 0.0),
    ]
    score = float(np.mean(score_components))

    return SqueezeSignal(
        symbol=symbol,
        score=score,
        gex_estimate=gex,
        near_strike_call_vol_ratio=near_call_vol_ratio,
        oi_skew=oi_skew,
        iv_rising_with_price=iv_rising_with_price,
        multi_strike_vol_pressure=multi_strike_count,
        alert=score >= SQUEEZE_THRESHOLD,
    )


def scan_watchlist(symbols: list[str] | None = None) -> list[SqueezeSignal]:
    from app.modules.tos.ml.research.sector_contagion import ALL_SYMBOLS
    targets = symbols or ALL_SYMBOLS
    results = [r for sym in targets if (r := analyze_symbol(sym)) is not None]
    return sorted(results, key=lambda x: -x.score)


def main():
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default=None)
    args = parser.parse_args()

    symbols = [args.symbol] if args.symbol else None
    results = scan_watchlist(symbols)
    if not results:
        print("No data available.")
        return
    for sig in results:
        alert_tag = " *** SQUEEZE ALERT ***" if sig.alert else ""
        print(f"{sig.symbol}: score={sig.score:.3f}{alert_tag}")
        for k, v in sig.to_dict().items():
            if k not in ("symbol", "score"):
                print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
