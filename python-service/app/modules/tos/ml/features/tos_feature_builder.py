"""
Feature builder for the TOS unusual-volume ML pipeline.

Loads labeled events from the TOS MCP server's signal_catalog (Postgres)
and enriches them with time-series context from TOS QuestDB.

Two entry points:
  load_training_data()   — batch load for model training
  build_event_features() — single event vector for real-time inference
"""
import math
import warnings
from datetime import datetime, timedelta, timezone
from typing import Optional

import numpy as np
import pandas as pd

from app.modules.tos.db.tos_db import get_tos_postgres, get_tos_questdb

# ---------------------------------------------------------------------------
# Feature column lists (single source of truth consumed by all models)
# ---------------------------------------------------------------------------

CONTRACT_FEATURES = [
    "volume_ratio_10d",
    "volume_ratio_20d",
    "vol_oi_ratio",
    "premium_total",
    "log_premium_total",
    "otm_pct",
    "days_to_expiry",
    "dte_bucket",       # 0=weekly, 1=biweekly, 2=monthly, 3=quarterly
    "is_call",
    "delta_abs",
    "gamma",
    "theta_per_day",
    "vega",
    "theta_vega_ratio",
    "ba_spread_pct",
    "iv_at_event",
    "iv_vs_hv_ratio",
    "hour_of_day",
    "is_morning",
    "is_afternoon",
]

UNDERLYING_CONTEXT_FEATURES = [
    "underlying_return_1d",
    "underlying_return_5d",
    "underlying_return_20d",
    "underlying_rsi_14",
    "underlying_vol_ratio_20d",
    "iv_rank",
    "iv_percentile",
    "iv_hv_ratio",
    "atm_iv",
    "skew_25d",
    "term_slope",
    "iv_change_1d",
    "put_call_ratio_1d",
    "unusual_events_count_1d",
    "unusual_events_count_5d",
    "call_bias_today",
    "days_to_earnings",
    "is_within_2w_earnings",
    "is_post_earnings",
    "vix_level",
    "spy_return_5d",
    "spy_return_20d",
    "vix_percentile_60d",
]

CLUSTER_FEATURES = [
    "cluster_contract_count",
    "cluster_call_put_ratio",
    "cluster_total_premium",
    "cluster_strike_dispersion",
    "cluster_dte_range",
    "cluster_weighted_delta",
    "is_isolated_event",
]

HISTORICAL_TICKER_FEATURES = [
    "ticker_signal_hit_rate_30d",
    "ticker_signal_count_30d",
    "ticker_avg_return_5d_after",
    "ticker_avg_premium_30d",
]

ALL_FEATURES = (
    CONTRACT_FEATURES
    + UNDERLYING_CONTEXT_FEATURES
    + CLUSTER_FEATURES
    + HISTORICAL_TICKER_FEATURES
)

# Features used only for direction models (macro context, not contract geometry)
DIRECTION_FEATURES = UNDERLYING_CONTEXT_FEATURES + CLUSTER_FEATURES + HISTORICAL_TICKER_FEATURES

# Features used for regime classification
REGIME_FEATURES = [
    "vix_level",
    "vix_1w_change",
    "vix_percentile_60d",
    "spy_return_5d",
    "spy_return_20d",
    "spy_rsi_14",
    "spy_vol_ratio_20d",
    "watchlist_avg_iv_rank",
    "watchlist_avg_skew",
    "spy_term_slope",
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _dte_bucket(dte: int) -> int:
    if dte <= 7:   return 0  # weekly
    if dte <= 14:  return 1  # biweekly
    if dte <= 30:  return 2  # monthly
    return 3                 # quarterly

def _rsi(prices: pd.Series, period: int = 14) -> float:
    if len(prices) < period + 1:
        return 50.0
    delta = prices.diff().dropna()
    gains = delta.where(delta > 0, 0.0)
    losses = -delta.where(delta < 0, 0.0)
    avg_gain = gains.rolling(period).mean().iloc[-1]
    avg_loss = losses.rolling(period).mean().iloc[-1]
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))

def _safe_div(a, b, default=0.0):
    try:
        return float(a) / float(b) if b and b != 0 else default
    except (TypeError, ZeroDivisionError):
        return default

# ---------------------------------------------------------------------------
# Batch loader for training
# ---------------------------------------------------------------------------

def load_training_data(
    min_labeled_days: int = 5,
    min_rows: int = 100,
    symbol: Optional[str] = None,
) -> pd.DataFrame:
    """
    Load fully-labeled signal events from TOS postgres + enrich with context.

    Returns a DataFrame with ALL_FEATURES columns plus label columns:
      quality_signal, direction_correct_5d, underlying_return_5d_fwd,
      underlying_return_10d_fwd, mfe_5d, mae_5d, option_return_5d,
      realized_within_2d, option_type, detected_at
    """
    pg = get_tos_postgres()

    # Rows where 5d follow-through is filled (T+5 has elapsed)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=min_labeled_days)).isoformat()
    sym_filter = "AND symbol = %(symbol)s" if symbol else ""

    catalog_q = f"""
        SELECT
            id, detected_at, symbol, expiry, days_to_expiry, strike,
            option_type, moneyness, otm_pct,
            volume, volume_ratio_20d, premium_total, implied_vol, iv_rank,
            delta, underlying_price, underlying_return_1d,
            underlying_return_5d AS underlying_return_5d_prior,
            iv_hv_ratio, put_call_ratio_1d, days_to_earnings,
            vix_at_detection AS vix_level, spy_return_5d,
            -- follow-through labels
            underlying_return_1d_fwd,
            underlying_return_5d_fwd,
            underlying_return_10d_fwd,
            underlying_max_fav_5d  AS mfe_5d,
            underlying_max_adv_5d  AS mae_5d,
            option_return_5d,
            direction_correct,
            move_5d_exceeded_2pct
        FROM signal_catalog
        WHERE underlying_return_5d_fwd IS NOT NULL
          AND detected_at <= %(cutoff)s
          {sym_filter}
        ORDER BY detected_at
    """
    with pg.cursor() as cur:
        cur.execute(catalog_q, {"cutoff": cutoff, "symbol": symbol})
        rows = cur.fetchall()

    if len(rows) < min_rows:
        raise ValueError(
            f"Only {len(rows)} labeled rows available (need {min_rows}). "
            "Wait for more follow-through data or lower min_rows."
        )

    df = pd.DataFrame([dict(r) for r in rows])
    df["detected_at"] = pd.to_datetime(df["detected_at"], utc=True)

    # Derived labels
    df["quality_signal"] = (
        df["direction_correct"].fillna(False)
        & df["move_5d_exceeded_2pct"].fillna(False)
    ).astype(int)
    df["direction_correct_5d"] = df["direction_correct"].fillna(False).astype(int)
    df["realized_within_2d"] = (
        df["underlying_return_1d_fwd"].abs() > 0.01
    ).astype(int)

    # Enrich with Greeks + spread from unusual_volume_events
    df = _enrich_greeks(df, pg)

    # Enrich with IV surface features
    df = _enrich_iv_surface(df)

    # Enrich with cluster features
    df = _enrich_clusters(df, pg)

    # Compute session + derived contract features
    df = _compute_contract_features(df)

    # Compute historical ticker features (look-back, no leakage)
    df = _compute_historical_ticker_features(df)

    # Enrich SPY/VIX context (20d return, RSI, percentile)
    df = _enrich_spy_vix_context(df)

    pg.close()

    # Fill remaining NaNs with 0
    df[ALL_FEATURES] = df[ALL_FEATURES].fillna(0.0)

    return df

# ---------------------------------------------------------------------------
# Feature enrichment helpers
# ---------------------------------------------------------------------------

def _enrich_greeks(df: pd.DataFrame, pg) -> pd.DataFrame:
    """Join gamma, theta, vega, ba_spread_pct from unusual_volume_events."""
    ids = tuple(df["id"].astype(str).tolist())
    if not ids:
        return df

    # Unusual volume events are stored in TOS postgres signal_catalog already.
    # Greeks and spread are in the options_unusual_volume_events QuestDB table.
    # We match on (symbol, expiry, strike, option_type, detected_ts within 10min).
    qdb = get_tos_questdb()
    try:
        rows = []
        for _, row in df.iterrows():
            ts = row["detected_at"]
            ts_lo = (ts - timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%S")
            ts_hi = (ts + timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%S")
            cur = qdb.cursor()
            cur.execute(
                """
                SELECT gamma, theta, vega, ba_spread_pct, volume_ratio_10d,
                       open_interest, underlying_vol_ratio_20d
                FROM options_unusual_volume_events
                WHERE underlying_symbol = %s
                  AND strike = %s
                  AND option_type = %s
                  AND detected_ts >= %s
                  AND detected_ts <= %s
                LIMIT 1
                """,
                (row["symbol"], float(row["strike"]), row["option_type"], ts_lo, ts_hi),
            )
            r = cur.fetchone()
            cur.close()
            rows.append(r)

        greek_df = pd.DataFrame(
            rows,
            columns=["gamma", "theta", "vega", "ba_spread_pct",
                     "volume_ratio_10d", "open_interest", "underlying_vol_ratio_20d"],
            index=df.index,
        )
        df = pd.concat([df, greek_df], axis=1)
    except Exception as exc:
        warnings.warn(f"Greeks enrichment failed (TOS QuestDB unavailable?): {exc}")
        for col in ["gamma", "theta", "vega", "ba_spread_pct",
                    "volume_ratio_10d", "open_interest", "underlying_vol_ratio_20d"]:
            df[col] = 0.0
    finally:
        qdb.close()

    return df


def _enrich_iv_surface(df: pd.DataFrame) -> pd.DataFrame:
    """
    Pull atm_iv, skew_25d, term_slope, iv_percentile, iv_change_1d
    from iv_surface_snapshots (TOS QuestDB) at detection time.
    """
    qdb = get_tos_questdb()
    atm_ivs, skew_25ds, term_slopes, iv_pcts, iv_chg1ds = [], [], [], [], []

    try:
        cur = qdb.cursor()
        for _, row in df.iterrows():
            ts = row["detected_at"]
            ts_str = ts.strftime("%Y-%m-%dT%H:%M:%S")
            ts_prev = (ts - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")

            cur.execute(
                """
                SELECT atm_iv, skew_25d, term_slope, iv_percentile
                FROM iv_surface_snapshots
                WHERE symbol = %s
                  AND snapshot_ts <= %s
                ORDER BY snapshot_ts DESC
                LIMIT 1
                """,
                (row["symbol"], ts_str),
            )
            snap = cur.fetchone()

            # Prior day for iv_change_1d
            cur.execute(
                """
                SELECT iv_rank
                FROM iv_surface_snapshots
                WHERE symbol = %s
                  AND snapshot_ts <= %s
                ORDER BY snapshot_ts DESC
                LIMIT 1
                """,
                (row["symbol"], ts_prev),
            )
            prev_snap = cur.fetchone()

            if snap:
                atm_ivs.append(snap[0])
                skew_25ds.append(snap[1])
                term_slopes.append(snap[2])
                iv_pcts.append(snap[3])
            else:
                atm_ivs.append(None)
                skew_25ds.append(None)
                term_slopes.append(None)
                iv_pcts.append(None)

            prior_rank = prev_snap[0] if prev_snap else None
            iv_chg1ds.append(
                float(row["iv_rank"]) - float(prior_rank)
                if prior_rank is not None else 0.0
            )
        cur.close()
    except Exception as exc:
        warnings.warn(f"IV surface enrichment failed: {exc}")
        atm_ivs = [0.0] * len(df)
        skew_25ds = [0.0] * len(df)
        term_slopes = [0.0] * len(df)
        iv_pcts = [50.0] * len(df)
        iv_chg1ds = [0.0] * len(df)
    finally:
        qdb.close()

    df["atm_iv"]      = atm_ivs
    df["skew_25d"]    = skew_25ds
    df["term_slope"]  = term_slopes
    df["iv_percentile"] = iv_pcts
    df["iv_change_1d"]  = iv_chg1ds
    return df


def _enrich_clusters(df: pd.DataFrame, pg) -> pd.DataFrame:
    """Join cluster features from signal_clusters (TOS postgres)."""
    try:
        with pg.cursor() as cur:
            cur.execute(
                """
                SELECT sc.id AS signal_id,
                       cl.contract_count  AS cluster_contract_count,
                       cl.call_count::float / NULLIF(cl.put_count, 0) AS cluster_call_put_ratio,
                       cl.total_premium   AS cluster_total_premium,
                       cl.strike_range_pct AS cluster_strike_dispersion,
                       cl.dte_range       AS cluster_dte_range,
                       cl.weighted_delta  AS cluster_weighted_delta
                FROM signal_catalog sc
                LEFT JOIN signal_clusters cl
                  ON sc.id = ANY(cl.signal_ids::uuid[])
                WHERE sc.id = ANY(%s::uuid[])
                """,
                (list(df["id"].astype(str)),),
            )
            cluster_rows = {str(r["signal_id"]): dict(r) for r in cur.fetchall()}
    except Exception as exc:
        warnings.warn(f"Cluster enrichment failed: {exc}")
        cluster_rows = {}

    for col in ["cluster_contract_count", "cluster_call_put_ratio",
                "cluster_total_premium", "cluster_strike_dispersion",
                "cluster_dte_range", "cluster_weighted_delta"]:
        df[col] = df["id"].astype(str).map(
            lambda sid: cluster_rows.get(sid, {}).get(col, 0.0)
        )
    df["is_isolated_event"] = (df["cluster_contract_count"].fillna(0) == 0).astype(int)
    return df


def _compute_contract_features(df: pd.DataFrame) -> pd.DataFrame:
    """Pure derivations from columns already in df."""
    dt = df["detected_at"].dt
    df["hour_of_day"]   = dt.hour + dt.minute / 60.0
    df["is_morning"]    = ((dt.hour == 9) & (dt.minute >= 30) | (dt.hour == 10)).astype(int)
    df["is_afternoon"]  = (dt.hour >= 14).astype(int)
    df["is_call"]       = (df["option_type"] == "C").astype(int)
    df["delta_abs"]     = df["delta"].abs()
    df["dte_bucket"]    = df["days_to_expiry"].apply(_dte_bucket)
    df["log_premium_total"] = np.log1p(df["premium_total"].clip(lower=0))
    df["theta_per_day"] = df.get("theta", 0.0)
    df["theta_vega_ratio"] = df.apply(
        lambda r: _safe_div(r.get("theta", 0.0), r.get("vega", 0.0)), axis=1
    )
    df["iv_vs_hv_ratio"] = df["iv_hv_ratio"]
    df["iv_at_event"]   = df["implied_vol"]

    df["is_within_2w_earnings"] = (
        df["days_to_earnings"].between(0, 14, inclusive="both")
    ).astype(int)
    df["is_post_earnings"] = (
        df["days_to_earnings"].between(-5, -1, inclusive="both")
    ).astype(int)
    df["unusual_events_count_1d"] = 0  # filled by _compute_historical_ticker_features
    df["unusual_events_count_5d"] = 0
    df["call_bias_today"] = 0.0
    return df


def _compute_historical_ticker_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    For each row, compute look-back metrics from PRIOR rows of the same symbol.
    Strictly causal — never uses future data.
    """
    df = df.sort_values("detected_at").reset_index(drop=True)

    hit_rate_30d, count_30d, avg_ret_30d, avg_prem_30d = [], [], [], []
    ev_count_1d, ev_count_5d, call_bias = [], [], []

    for i, row in df.iterrows():
        ts = row["detected_at"]
        sym = row["symbol"]

        window_30 = df[
            (df["symbol"] == sym) &
            (df["detected_at"] < ts) &
            (df["detected_at"] >= ts - pd.Timedelta(days=30))
        ]
        window_1d = df[
            (df["symbol"] == sym) &
            (df["detected_at"] < ts) &
            (df["detected_at"] >= ts - pd.Timedelta(days=1))
        ]
        window_5d = df[
            (df["symbol"] == sym) &
            (df["detected_at"] < ts) &
            (df["detected_at"] >= ts - pd.Timedelta(days=5))
        ]

        if len(window_30) > 0 and "direction_correct_5d" in window_30.columns:
            labeled = window_30.dropna(subset=["direction_correct_5d"])
            hit_rate_30d.append(labeled["direction_correct_5d"].mean() if len(labeled) else 0.5)
            avg_ret = window_30["underlying_return_5d_fwd"].dropna().mean()
            avg_ret_30d.append(avg_ret if not np.isnan(avg_ret) else 0.0)
        else:
            hit_rate_30d.append(0.5)
            avg_ret_30d.append(0.0)

        count_30d.append(len(window_30))
        avg_prem_30d.append(window_30["premium_total"].mean() if len(window_30) else 0.0)

        ev_count_1d.append(len(window_1d))
        ev_count_5d.append(len(window_5d))

        if len(window_1d) > 0:
            calls_today = (window_1d["option_type"] == "C").sum()
            puts_today  = (window_1d["option_type"] == "P").sum()
            total_today = calls_today + puts_today
            call_bias.append(_safe_div(calls_today - puts_today, total_today))
        else:
            call_bias.append(0.0)

    df["ticker_signal_hit_rate_30d"] = hit_rate_30d
    df["ticker_signal_count_30d"]    = count_30d
    df["ticker_avg_return_5d_after"] = avg_ret_30d
    df["ticker_avg_premium_30d"]     = avg_prem_30d
    df["unusual_events_count_1d"]    = ev_count_1d
    df["unusual_events_count_5d"]    = ev_count_5d
    df["call_bias_today"]            = call_bias

    return df


def _enrich_spy_vix_context(df: pd.DataFrame) -> pd.DataFrame:
    """Pull SPY/VIX 20d return, RSI, and VIX percentile from TOS QuestDB bars."""
    qdb = get_tos_questdb()
    spy_ret20, spy_rsi, vix_pct60 = [], [], []

    try:
        cur = qdb.cursor()
        for _, row in df.iterrows():
            ts_str = row["detected_at"].strftime("%Y-%m-%dT%H:%M:%S")
            ts_60d = (row["detected_at"] - timedelta(days=65)).strftime("%Y-%m-%dT%H:%M:%S")

            cur.execute(
                """
                SELECT close
                FROM underlying_intraday_bars
                WHERE symbol = 'SPY'
                  AND resolution = '1d'
                  AND bar_ts <= %s
                ORDER BY bar_ts DESC
                LIMIT 25
                """,
                (ts_str,),
            )
            spy_bars = [r[0] for r in cur.fetchall()]

            if len(spy_bars) >= 20:
                spy_ser = pd.Series(spy_bars[::-1])
                spy_ret20.append(float((spy_ser.iloc[-1] / spy_ser.iloc[-21] - 1)
                                       if len(spy_ser) > 20 else 0.0))
                spy_rsi.append(_rsi(spy_ser))
            else:
                spy_ret20.append(0.0)
                spy_rsi.append(50.0)

            # VIX percentile over 60d
            cur.execute(
                """
                SELECT close
                FROM underlying_intraday_bars
                WHERE symbol = 'VIX'
                  AND resolution = '1d'
                  AND bar_ts >= %s
                  AND bar_ts <= %s
                ORDER BY bar_ts
                """,
                (ts_60d, ts_str),
            )
            vix_hist = [r[0] for r in cur.fetchall()]
            if len(vix_hist) >= 2:
                current = row.get("vix_level", vix_hist[-1])
                pct = float(sum(1 for v in vix_hist if v <= current) / len(vix_hist) * 100)
                vix_pct60.append(pct)
            else:
                vix_pct60.append(50.0)

        cur.close()
    except Exception as exc:
        warnings.warn(f"SPY/VIX enrichment failed: {exc}")
        n = len(df)
        spy_ret20 = [0.0] * n
        spy_rsi   = [50.0] * n
        vix_pct60 = [50.0] * n
    finally:
        qdb.close()

    df["spy_return_20d"]    = spy_ret20
    df["spy_rsi_14"]        = spy_rsi
    df["vix_percentile_60d"] = vix_pct60
    df["underlying_rsi_14"] = 50.0  # single-event RSI requires per-symbol bars; stubbed here
    df["underlying_return_20d"] = 0.0  # filled from signal_catalog if stored, else 0
    df["underlying_vol_ratio_20d"] = df.get("underlying_vol_ratio_20d", 0.0)
    return df

# ---------------------------------------------------------------------------
# Single-event inference vector
# ---------------------------------------------------------------------------

def build_event_features(
    signal_id: str,
    features: Optional[list] = None,
) -> dict:
    """
    Build a single feature dict for real-time inference.
    Fetches from TOS postgres + QuestDB for one signal ID.

    Returns a dict keyed by feature name, values as float.
    """
    pg = get_tos_postgres()
    with pg.cursor() as cur:
        cur.execute(
            "SELECT * FROM signal_catalog WHERE id = %s", (signal_id,)
        )
        row = cur.fetchone()
    pg.close()

    if row is None:
        raise ValueError(f"Signal {signal_id} not found in signal_catalog")

    df = pd.DataFrame([dict(row)])
    df["detected_at"] = pd.to_datetime(df["detected_at"], utc=True)
    # Re-use training enrichment pipeline on single row
    pg2 = get_tos_postgres()
    df = _enrich_greeks(df, pg2)
    df = _enrich_iv_surface(df)
    df = _enrich_clusters(df, pg2)
    df = _compute_contract_features(df)
    df = _compute_historical_ticker_features(df)
    df = _enrich_spy_vix_context(df)
    pg2.close()

    target_cols = features or ALL_FEATURES
    df[target_cols] = df[target_cols].fillna(0.0)
    return df[target_cols].iloc[0].to_dict()
