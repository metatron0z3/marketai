"""
Unusual volume detector — compares chain snapshots against volume baselines
and emits signal_catalog rows for qualifying events.

Thresholds (from tos-mcp-server-plan.md):
  volume_ratio_20d >= 3.0
  volume >= 500 contracts
  premium_total >= $50,000
  MIN_DTE=1, MAX_DTE=90
"""
import logging
import uuid
from datetime import datetime, timezone

from config import (
    CHAIN_MAX_DTE as MAX_DTE,
    CHAIN_MIN_DTE as MIN_DTE,
    UV_MIN_PREMIUM as MIN_PREMIUM,
    UV_MIN_VOLUME as MIN_VOLUME,
    UV_VOLUME_RATIO_THRESHOLD as VOLUME_RATIO_THRESHOLD,
)

log = logging.getLogger(__name__)


def compute_baselines(chain_rows: list[dict]) -> dict[tuple, dict]:
    """
    Compute per-contract rolling statistics from a list of historical chain rows.

    Input: chain rows with fields (underlying_symbol, strike, option_type, expiry, volume)
    Returns: {(symbol, strike, option_type, expiry): {avg_vol_10d, avg_vol_20d, ...}}

    Groups rows by contract key and computes rolling averages.
    Used for bootstrapping options_volume_baseline from historical snapshots.
    """
    from collections import defaultdict
    import numpy as np

    groups: dict[tuple, list[int]] = defaultdict(list)
    for row in chain_rows:
        key = (
            row["underlying_symbol"],
            row["strike"],
            row["option_type"],
            str(row["expiry"]),
        )
        groups[key].append(int(row["volume"] or 0))

    baselines = {}
    for key, volumes in groups.items():
        vols = [v for v in volumes if v > 0]
        if not vols:
            continue
        baselines[key] = {
            "avg_vol_10d": float(np.mean(vols[-10:])) if len(vols) >= 5 else float(np.mean(vols)),
            "avg_vol_20d": float(np.mean(vols[-20:])) if len(vols) >= 10 else float(np.mean(vols)),
            "median_vol":  float(np.median(vols)),
            "n_days":      len(vols),
        }
    return baselines


def detect_unusual_events(
    snapshot_rows: list[dict],
    baselines: dict[tuple, dict],
    prev_snapshot_rows: list[dict] | None = None,
) -> list[dict]:
    """
    Scan a chain snapshot for unusual volume events.

    snapshot_rows:      Current snapshot (from chain_collector)
    baselines:          From compute_baselines() or loaded from Postgres
    prev_snapshot_rows: Previous 5-min snapshot for sweep detection (None = skip)

    Returns: list of signal_candidate dicts (not yet written to signal_catalog).
    """
    prev_vols: dict[tuple, int] = {}
    if prev_snapshot_rows:
        for r in prev_snapshot_rows:
            key = (r["underlying_symbol"], r["strike"], r["option_type"], str(r["expiry"]))
            prev_vols[key] = int(r["volume"] or 0)

    events = []
    for row in snapshot_rows:
        symbol     = row["underlying_symbol"]
        strike     = row["strike"]
        opt_type   = row["option_type"]
        expiry_str = str(row["expiry"])
        dte        = int(row["days_to_expiry"])
        volume     = int(row["volume"] or 0)
        mark       = float(row["mark"] or 0)
        underlying = float(row["underlying_price"] or 0)

        if not (MIN_DTE <= dte <= MAX_DTE):
            continue
        if volume < MIN_VOLUME:
            continue

        premium = mark * volume * 100
        if premium < MIN_PREMIUM:
            continue

        key = (symbol, strike, opt_type, expiry_str)
        baseline = baselines.get(key)
        if not baseline or baseline["avg_vol_20d"] < 10:
            continue  # not enough history to establish baseline

        ratio_20d = volume / baseline["avg_vol_20d"]
        ratio_10d = volume / max(baseline["avg_vol_10d"], 1)

        if ratio_20d < VOLUME_RATIO_THRESHOLD:
            continue

        # OTM calculation
        if opt_type == "C":
            otm_pct = (strike - underlying) / underlying if underlying > 0 else 0
        else:
            otm_pct = (underlying - strike) / underlying if underlying > 0 else 0
        in_the_money = otm_pct < 0

        # Sweep detection: volume spike since last snapshot
        prev_vol = prev_vols.get(key, 0)
        vol_delta = volume - prev_vol
        is_sweep = vol_delta > 1000 and vol_delta / max(prev_vol, 1) > 2.0

        # Moneyness label
        if abs(otm_pct) < 0.01:
            moneyness = "ATM"
        elif otm_pct > 0:
            moneyness = "OTM"
        else:
            moneyness = "ITM"

        snapshot_ts: datetime = row["snapshot_ts"]
        hour = snapshot_ts.hour - 4  # ET (rough)
        is_morning   = 9 <= hour < 11
        is_afternoon = 14 <= hour < 16
        session      = "REGULAR"
        if hour < 9:
            session = "PREMARKET"
        elif hour >= 16:
            session = "AFTERHOURS"

        events.append({
            "signal_id":            str(uuid.uuid4()),
            "detected_at":          snapshot_ts,
            "symbol":               symbol,
            "option_type":          opt_type,
            "strike":               strike,
            "expiry_date":          expiry_str,
            "days_to_expiry":       dte,
            "moneyness":            moneyness,
            "otm_pct":              round(otm_pct, 4),
            "volume":               volume,
            "prior_snapshot_volume": prev_vol,
            "volume_delta":         vol_delta,
            "avg_volume_10d":       round(baseline["avg_vol_10d"], 1),
            "avg_volume_20d":       round(baseline["avg_vol_20d"], 1),
            "volume_ratio_10d":     round(ratio_10d, 2),
            "volume_ratio_20d":     round(ratio_20d, 2),
            "open_interest":        int(row.get("open_interest") or 0),
            "vol_oi_ratio":         round(volume / max(int(row.get("open_interest") or 1), 1), 3),
            "bid":                  float(row.get("bid") or 0),
            "ask":                  float(row.get("ask") or 0),
            "mark":                 mark,
            "ba_spread_pct":        float(row.get("ba_spread_pct") or 0),
            "implied_vol":          float(row.get("implied_vol") or 0),
            "iv_rank":              float(row.get("iv_rank") or 0),
            "iv_percentile":        float(row.get("iv_percentile") or 0),
            "delta":                float(row.get("delta") or 0),
            "gamma":                float(row.get("gamma") or 0),
            "theta":                float(row.get("theta") or 0),
            "vega":                 float(row.get("vega") or 0),
            "underlying_price":     underlying,
            "premium_total":        round(premium, 2),
            "notional_value":       round(underlying * abs(float(row.get("delta") or 0)) * volume * 100, 2),
            "is_sweep":             is_sweep,
            "is_call":              opt_type == "C",
            "in_the_money":         in_the_money,
            "hour_of_day":          snapshot_ts.hour,
            "is_morning":           is_morning,
            "is_afternoon":         is_afternoon,
            "session":              session,
            "detection_method":     "chain_diff",
            # follow-through columns (filled by EOD label job):
            "underlying_return_1d_fwd":  None,
            "underlying_return_5d_fwd":  None,
            "direction_correct_5d":      None,
            "quality_signal":            None,
            "option_return_5d":          None,
        })

    log.info("Detected %d unusual events from %d chain rows", len(events), len(snapshot_rows))
    return events
