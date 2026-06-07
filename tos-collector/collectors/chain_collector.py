"""
Options chain collector — pulls and normalizes Schwab chain data into
flat rows ready for QuestDB ingestion.

Schwab's chain response is nested by expiry date → strike → option type.
This module flattens it into one row per contract per snapshot.
"""
import logging
from datetime import date, datetime, timezone
from typing import Iterator

from collectors.schwab_client import get_client
from config import CHAIN_MAX_DTE, CHAIN_MIN_DTE, WATCHLIST

log = logging.getLogger(__name__)

# Only collect contracts within this DTE range
MIN_DTE = CHAIN_MIN_DTE
MAX_DTE = CHAIN_MAX_DTE


def _safe(d: dict, *keys, default=None):
    """Safe nested dict access."""
    cur = d
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k, default)
    return cur


def parse_chain_response(
    raw: dict,
    symbol: str,
    snapshot_ts: datetime,
) -> Iterator[dict]:
    """
    Flatten a Schwab chain response into individual contract rows.

    Yields one dict per contract, matching the options_chain_snapshots schema.
    """
    underlying_price = _safe(raw, "underlying", "last", default=0.0)

    for option_type_key in ("callExpDateMap", "putExpDateMap"):
        is_call = option_type_key == "callExpDateMap"
        expiry_map = raw.get(option_type_key, {})

        for expiry_str, strikes in expiry_map.items():
            # expiry_str format: "2025-01-17:21" (date:dte)
            try:
                expiry_date_str = expiry_str.split(":")[0]
                expiry_dt = date.fromisoformat(expiry_date_str)
                dte = (expiry_dt - snapshot_ts.date()).days
            except (ValueError, IndexError):
                continue

            if not (MIN_DTE <= dte <= MAX_DTE):
                continue

            for strike_str, contracts in strikes.items():
                if not contracts:
                    continue
                c = contracts[0]  # Schwab returns a list with one contract per strike

                try:
                    strike = float(strike_str)
                    bid    = float(_safe(c, "bid",          default=0) or 0)
                    ask    = float(_safe(c, "ask",          default=0) or 0)
                    last   = float(_safe(c, "last",         default=0) or 0)
                    mark   = float(_safe(c, "mark",         default=0) or 0)
                    volume = int(_safe(c,   "totalVolume",  default=0) or 0)
                    oi     = int(_safe(c,   "openInterest", default=0) or 0)
                    iv     = float(_safe(c, "volatility",   default=0) or 0) / 100
                    delta  = float(_safe(c, "delta",        default=0) or 0)
                    gamma  = float(_safe(c, "gamma",        default=0) or 0)
                    theta  = float(_safe(c, "theta",        default=0) or 0)
                    vega   = float(_safe(c, "vega",         default=0) or 0)
                    rho    = float(_safe(c, "rho",          default=0) or 0)
                    iv_rank    = float(_safe(c, "ivrank",       default=0) or 0)
                    iv_pct     = float(_safe(c, "ivPercentile", default=0) or 0)
                    intrinsic  = float(_safe(c, "intrinsicValue", default=0) or 0)
                    extrinsic  = float(_safe(c, "extrinsicValue", default=0) or 0)
                    theo       = float(_safe(c, "theoreticalOptionValue", default=0) or 0)
                    bid_sz     = int(_safe(c,   "bidSize",      default=0) or 0)
                    ask_sz     = int(_safe(c,   "askSize",      default=0) or 0)
                    open_pr    = float(_safe(c, "openPrice",    default=0) or 0)
                    high_pr    = float(_safe(c, "highPrice",    default=0) or 0)
                    low_pr     = float(_safe(c, "lowPrice",     default=0) or 0)
                    net_chg    = float(_safe(c, "netChange",    default=0) or 0)
                    in_money   = bool(_safe(c,  "inTheMoney",   default=False))
                    multiplier = int(_safe(c,   "multiplier",   default=100) or 100)
                except (TypeError, ValueError) as e:
                    log.debug("Parse error for %s %s %s: %s", symbol, expiry_str, strike_str, e)
                    continue

                ba_spread_pct = ((ask - bid) / mark) if mark > 0 else 0.0

                yield {
                    "snapshot_ts":      snapshot_ts,
                    "underlying_symbol": symbol,
                    "expiry":           expiry_dt,
                    "days_to_expiry":   dte,
                    "strike":           strike,
                    "option_type":      "C" if is_call else "P",
                    "bid":              bid,
                    "ask":              ask,
                    "last":             last,
                    "mark":             mark,
                    "volume":           volume,
                    "open_interest":    oi,
                    "delta":            delta,
                    "gamma":            gamma,
                    "theta":            theta,
                    "vega":             vega,
                    "rho":              rho,
                    "implied_vol":      iv,
                    "iv_rank":          iv_rank,
                    "iv_percentile":    iv_pct,
                    "underlying_price": underlying_price,
                    "in_the_money":     in_money,
                    "theo_price":       theo,
                    "intrinsic_value":  intrinsic,
                    "extrinsic_value":  extrinsic,
                    "bid_size":         bid_sz,
                    "ask_size":         ask_sz,
                    "open_price":       open_pr,
                    "high_price":       high_pr,
                    "low_price":        low_pr,
                    "net_change":       net_chg,
                    "ba_spread_pct":    ba_spread_pct,
                    "multiplier":       multiplier,
                }


def collect_snapshot(symbol: str, as_of_date: str | None = None) -> list[dict]:
    """
    Pull and parse a full chain snapshot for one symbol.
    as_of_date: "YYYY-MM-DD" for historical pulls (None = live).
    """
    client = get_client()
    snapshot_ts = datetime.now(tz=timezone.utc)

    kwargs: dict = {"symbol": symbol, "strike_count": 200}
    if as_of_date:
        kwargs["from_date"] = as_of_date
        kwargs["to_date"]   = as_of_date

    log.info("Pulling chain: %s (as_of=%s)", symbol, as_of_date or "live")
    raw = client.get_chains(**kwargs)
    rows = list(parse_chain_response(raw, symbol, snapshot_ts))
    log.info("  → %d contracts parsed", len(rows))
    return rows


def collect_iv_surface(symbol: str) -> dict | None:
    """
    Derive IV surface metrics from a chain snapshot.
    Returns: {atm_iv, skew_25d, term_slope, iv_rank, iv_percentile, snapshot_ts}
    """
    rows = collect_snapshot(symbol)
    if not rows:
        return None

    underlying = rows[0]["underlying_price"]
    snapshot_ts = rows[0]["snapshot_ts"]

    # ATM contracts: within 2% of spot, 25-35 DTE
    monthly = [r for r in rows if 25 <= r["days_to_expiry"] <= 35
               and abs(r["strike"] - underlying) / underlying < 0.02]
    quarterly = [r for r in rows if 55 <= r["days_to_expiry"] <= 65
                 and abs(r["strike"] - underlying) / underlying < 0.02]

    atm_30d_calls = [r["implied_vol"] for r in monthly if r["option_type"] == "C"]
    atm_60d_calls = [r["implied_vol"] for r in quarterly if r["option_type"] == "C"]

    atm_iv   = (sum(atm_30d_calls) / len(atm_30d_calls)) if atm_30d_calls else 0
    atm_60d  = (sum(atm_60d_calls) / len(atm_60d_calls)) if atm_60d_calls else 0
    term_slope = (atm_60d - atm_iv) / 30 if atm_iv > 0 else 0

    # 25-delta skew: put_iv_25d - call_iv_25d for 25-35 DTE
    puts_25d  = [r["implied_vol"] for r in monthly
                 if r["option_type"] == "P" and 0.20 <= abs(r["delta"]) <= 0.30]
    calls_25d = [r["implied_vol"] for r in monthly
                 if r["option_type"] == "C" and 0.20 <= abs(r["delta"]) <= 0.30]
    put_iv_25d  = sum(puts_25d)  / len(puts_25d)  if puts_25d  else atm_iv
    call_iv_25d = sum(calls_25d) / len(calls_25d) if calls_25d else atm_iv
    skew_25d = put_iv_25d - call_iv_25d

    iv_rank = rows[0].get("iv_rank", 0)
    iv_pct  = rows[0].get("iv_percentile", 0)

    return {
        "snapshot_ts":   snapshot_ts,
        "symbol":        symbol,
        "atm_iv":        round(atm_iv, 4),
        "skew_25d":      round(skew_25d, 4),
        "term_slope":    round(term_slope, 6),
        "iv_rank":       iv_rank,
        "iv_percentile": iv_pct,
        "underlying_price": underlying,
    }
