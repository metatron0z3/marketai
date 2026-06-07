"""
Postgres writer — signal_catalog, options_volume_baseline, earnings_calendar.
"""
import logging
import os

import psycopg2
import psycopg2.extras

log = logging.getLogger(__name__)

POSTGRES_HOST = os.getenv("TOS_POSTGRES_HOST", "localhost")
POSTGRES_PORT = int(os.getenv("TOS_POSTGRES_PORT", "5433"))
POSTGRES_DB   = os.getenv("TOS_POSTGRES_DB",   "tos")
POSTGRES_USER = os.getenv("TOS_POSTGRES_USER", "tos_writer")
POSTGRES_PASS = os.getenv("TOS_POSTGRES_PASS", "tos_writer")


def get_conn():
    return psycopg2.connect(
        host=POSTGRES_HOST, port=POSTGRES_PORT,
        database=POSTGRES_DB, user=POSTGRES_USER,
        password=POSTGRES_PASS,
        cursor_factory=psycopg2.extras.RealDictCursor,
    )


def upsert_signals(signals: list[dict]) -> int:
    """
    Upsert signal_catalog rows. Uses signal_id as PK — safe to re-run.
    Returns number of rows inserted/updated.
    """
    if not signals:
        return 0

    conn = get_conn()
    try:
        written = 0
        with conn.cursor() as cur:
            for sig in signals:
                cur.execute("""
                    INSERT INTO signal_catalog (
                        signal_id, symbol, option_type, strike, expiry_date,
                        days_to_expiry, detected_at, moneyness, otm_pct,
                        volume, prior_snapshot_volume, volume_delta,
                        avg_volume_10d, avg_volume_20d,
                        volume_ratio_10d, volume_ratio_20d,
                        open_interest, vol_oi_ratio,
                        bid, ask, mark, ba_spread_pct,
                        implied_vol, iv_rank, iv_percentile,
                        delta, gamma, theta, vega,
                        underlying_price, premium_total, notional_value,
                        is_sweep, is_call, in_the_money,
                        hour_of_day, is_morning, is_afternoon, session,
                        detection_method,
                        underlying_return_1d_fwd, underlying_return_5d_fwd,
                        direction_correct_5d, quality_signal, option_return_5d,
                        created_at, updated_at
                    ) VALUES (
                        %(signal_id)s, %(symbol)s, %(option_type)s, %(strike)s,
                        %(expiry_date)s, %(days_to_expiry)s, %(detected_at)s,
                        %(moneyness)s, %(otm_pct)s,
                        %(volume)s, %(prior_snapshot_volume)s, %(volume_delta)s,
                        %(avg_volume_10d)s, %(avg_volume_20d)s,
                        %(volume_ratio_10d)s, %(volume_ratio_20d)s,
                        %(open_interest)s, %(vol_oi_ratio)s,
                        %(bid)s, %(ask)s, %(mark)s, %(ba_spread_pct)s,
                        %(implied_vol)s, %(iv_rank)s, %(iv_percentile)s,
                        %(delta)s, %(gamma)s, %(theta)s, %(vega)s,
                        %(underlying_price)s, %(premium_total)s, %(notional_value)s,
                        %(is_sweep)s, %(is_call)s, %(in_the_money)s,
                        %(hour_of_day)s, %(is_morning)s, %(is_afternoon)s,
                        %(session)s, %(detection_method)s,
                        %(underlying_return_1d_fwd)s, %(underlying_return_5d_fwd)s,
                        %(direction_correct_5d)s, %(quality_signal)s,
                        %(option_return_5d)s,
                        NOW(), NOW()
                    )
                    ON CONFLICT (signal_id) DO UPDATE SET
                        updated_at = NOW()
                """, sig)
                written += 1
        conn.commit()
        log.info("Upserted %d signals to signal_catalog", written)
        return written
    finally:
        conn.close()


def upsert_baselines(baselines: dict[tuple, dict]) -> int:
    """
    Write volume baselines to options_volume_baseline.
    Key: (symbol, strike, option_type, expiry_str)
    """
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            for (symbol, strike, option_type, expiry), stats in baselines.items():
                cur.execute("""
                    INSERT INTO options_volume_baseline
                    (symbol, strike, option_type, expiry_date,
                     avg_volume_10d, avg_volume_20d, median_volume, n_days,
                     updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (symbol, strike, option_type, expiry_date)
                    DO UPDATE SET
                        avg_volume_10d = EXCLUDED.avg_volume_10d,
                        avg_volume_20d = EXCLUDED.avg_volume_20d,
                        median_volume  = EXCLUDED.median_volume,
                        n_days         = EXCLUDED.n_days,
                        updated_at     = NOW()
                """, (symbol, strike, option_type, expiry,
                      stats["avg_vol_10d"], stats["avg_vol_20d"],
                      stats["median_vol"], stats["n_days"]))
        conn.commit()
        log.info("Upserted %d baselines", len(baselines))
        return len(baselines)
    finally:
        conn.close()


def load_baselines(symbols: list[str]) -> dict[tuple, dict]:
    """Load baselines from Postgres into memory for detection."""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            placeholders = ", ".join(["%s"] * len(symbols))
            cur.execute(f"""
                SELECT symbol, strike, option_type, expiry_date::text,
                       avg_volume_10d, avg_volume_20d, median_volume, n_days
                FROM   options_volume_baseline
                WHERE  symbol IN ({placeholders})
                  AND  updated_at > NOW() - INTERVAL '7 days'
            """, symbols)
            rows = cur.fetchall()

        return {
            (r["symbol"], float(r["strike"]), r["option_type"], r["expiry_date"]): {
                "avg_vol_10d": r["avg_volume_10d"],
                "avg_vol_20d": r["avg_volume_20d"],
                "median_vol":  r["median_volume"],
                "n_days":      r["n_days"],
            }
            for r in rows
        }
    finally:
        conn.close()


def upsert_earnings_calendar(entries: list[dict]) -> int:
    """
    entries: [{symbol, earnings_date, confirmed, eps_estimate, ...}]
    """
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            for e in entries:
                cur.execute("""
                    INSERT INTO earnings_calendar
                    (symbol, earnings_date, confirmed, eps_estimate, updated_at)
                    VALUES (%(symbol)s, %(earnings_date)s, %(confirmed)s,
                            %(eps_estimate)s, NOW())
                    ON CONFLICT (symbol, earnings_date) DO UPDATE SET
                        confirmed    = EXCLUDED.confirmed,
                        eps_estimate = EXCLUDED.eps_estimate,
                        updated_at   = NOW()
                """, e)
        conn.commit()
        return len(entries)
    finally:
        conn.close()
