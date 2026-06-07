"""
Follow-through label computer — fills signal_catalog return columns
from price history stored in underlying_intraday_bars.

Run nightly at 4:30 PM ET:
  - T+1 labels: for signals detected yesterday
  - T+5 labels: for signals detected 5 trading days ago

All computations are strictly causal: only price data AFTER the event timestamp
is used. No look-ahead.
"""
import logging
from datetime import datetime, timedelta, timezone

import psycopg2
import psycopg2.extras

log = logging.getLogger(__name__)

# Returns threshold for quality_signal composite label
MIN_MOVE_PCT = 0.02   # |5d return| > 2%


def compute_labels_for_signal(
    signal: dict,
    daily_closes: dict[str, float],  # {date_str: close_price}
) -> dict:
    """
    Compute all follow-through labels for one signal_catalog row.

    signal:       dict with signal_id, symbol, option_type, detected_at
    daily_closes: {YYYY-MM-DD: close} from underlying_intraday_bars for this symbol

    Returns: dict of label column values to upsert.
    """
    detected_at: datetime = signal["detected_at"]
    if detected_at.tzinfo is None:
        detected_at = detected_at.replace(tzinfo=timezone.utc)

    detect_date = detected_at.date()
    option_type = signal.get("option_type", "C")

    def close_n_days_fwd(n: int) -> float | None:
        """Get close price n trading days after detected_at."""
        target = detect_date
        found = 0
        for _ in range(n * 3):  # scan up to 3x to skip weekends/holidays
            target += timedelta(days=1)
            if str(target) in daily_closes:
                found += 1
                if found == n:
                    return daily_closes[str(target)]
        return None

    def close_on_date(d) -> float | None:
        return daily_closes.get(str(d))

    entry_price = close_on_date(detect_date) or close_n_days_fwd(0)
    if not entry_price:
        return {}   # no entry price → can't compute anything

    labels = {}

    # T+1
    close_1d = close_n_days_fwd(1)
    if close_1d and entry_price > 0:
        ret_1d = (close_1d - entry_price) / entry_price
        labels["underlying_return_1d_fwd"] = round(ret_1d, 6)

    # T+5
    close_5d = close_n_days_fwd(5)
    if close_5d and entry_price > 0:
        ret_5d = (close_5d - entry_price) / entry_price
        labels["underlying_return_5d_fwd"] = round(ret_5d, 6)

        # Direction: did the underlying move in the option's implied direction?
        if option_type == "C":
            direction_correct = 1 if ret_5d > 0 else 0
        else:
            direction_correct = 1 if ret_5d < 0 else 0

        labels["direction_correct_5d"]  = direction_correct
        labels["move_exceeded_2pct_5d"] = 1 if abs(ret_5d) > MIN_MOVE_PCT else 0
        labels["quality_signal"]        = (
            1 if direction_correct and abs(ret_5d) > MIN_MOVE_PCT else 0
        )

    return labels


def compute_all_pending_labels(pg_conn, questdb_conn) -> dict:
    """
    Fetch all unlabeled signal_catalog rows, compute labels, write back.

    Returns summary: {processed, labeled_1d, labeled_5d, skipped}
    """
    now = datetime.now(tz=timezone.utc)
    cutoff_1d = now - timedelta(days=1)
    cutoff_5d = now - timedelta(days=5)

    with pg_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""
            SELECT signal_id, symbol, option_type, detected_at,
                   underlying_return_1d_fwd, underlying_return_5d_fwd
            FROM   signal_catalog
            WHERE  (underlying_return_1d_fwd IS NULL AND detected_at <= %(d1)s)
               OR  (underlying_return_5d_fwd IS NULL AND detected_at <= %(d5)s)
            ORDER  BY detected_at
        """, {"d1": cutoff_1d, "d5": cutoff_5d})
        signals = list(cur.fetchall())

    log.info("Computing labels for %d pending signals", len(signals))

    # Load price history for all symbols needed
    symbols_needed = list({s["symbol"] for s in signals})
    price_cache: dict[str, dict[str, float]] = {}
    for sym in symbols_needed:
        price_cache[sym] = _load_daily_closes(questdb_conn, sym)

    processed = labeled_1d = labeled_5d = skipped = 0
    for signal in signals:
        sym = signal["symbol"]
        closes = price_cache.get(sym, {})
        if not closes:
            skipped += 1
            continue

        new_labels = compute_labels_for_signal(dict(signal), closes)
        if not new_labels:
            skipped += 1
            continue

        # Merge with existing (don't overwrite already-computed labels)
        update_cols = []
        update_vals = []
        if signal["underlying_return_1d_fwd"] is None and "underlying_return_1d_fwd" in new_labels:
            update_cols.append("underlying_return_1d_fwd = %s")
            update_vals.append(new_labels["underlying_return_1d_fwd"])
            labeled_1d += 1

        if signal["underlying_return_5d_fwd"] is None and "underlying_return_5d_fwd" in new_labels:
            for col in ("underlying_return_5d_fwd", "direction_correct_5d",
                        "move_exceeded_2pct_5d", "quality_signal"):
                if col in new_labels:
                    update_cols.append(f"{col} = %s")
                    update_vals.append(new_labels[col])
            labeled_5d += 1

        if not update_cols:
            skipped += 1
            continue

        update_cols.append("updated_at = NOW()")
        update_vals.append(signal["signal_id"])
        with pg_conn.cursor() as cur:
            cur.execute(
                f"UPDATE signal_catalog SET {', '.join(update_cols)} WHERE signal_id = %s",
                update_vals,
            )
        pg_conn.commit()
        processed += 1

    log.info("Labels: processed=%d 1d=%d 5d=%d skipped=%d",
             processed, labeled_1d, labeled_5d, skipped)
    return {
        "processed": processed,
        "labeled_1d": labeled_1d,
        "labeled_5d": labeled_5d,
        "skipped": skipped,
    }


def _load_daily_closes(questdb_conn, symbol: str) -> dict[str, float]:
    """Load {YYYY-MM-DD: close} from underlying_intraday_bars for past 30 days."""
    try:
        with questdb_conn.cursor() as cur:
            cur.execute("""
                SELECT ts::date AS d, close
                FROM   underlying_intraday_bars
                WHERE  symbol   = %(sym)s
                  AND  bar_size = '1d'
                  AND  ts > NOW() - INTERVAL '40 days'
                ORDER  BY ts
            """, {"sym": symbol})
            return {str(row[0]): float(row[1]) for row in cur.fetchall()}
    except Exception as e:
        log.warning("Could not load closes for %s: %s", symbol, e)
        return {}
