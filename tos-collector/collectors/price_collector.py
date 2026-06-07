"""
Underlying price collector — OHLCV bars from Schwab API.
Populates underlying_intraday_bars in TOS QuestDB.
"""
import logging
from datetime import datetime, timezone

from collectors.schwab_client import get_client
from config import WATCHLIST

log = logging.getLogger(__name__)


def collect_daily_ohlcv(symbol: str, years: int = 2) -> list[dict]:
    """
    Pull daily OHLCV going back `years` years.
    Returns list of bar dicts matching underlying_intraday_bars schema.
    """
    client = get_client()
    log.info("Pulling %dy daily OHLCV for %s", years, symbol)

    raw = client.get_price_history(
        symbol=symbol,
        period_type="year",
        period=min(years, 5),
        frequency_type="daily",
        frequency=1,
    )
    return _parse_bars(raw, symbol, "1d")


def collect_hourly_bars(symbol: str, months: int = 6) -> list[dict]:
    """Pull hourly bars going back `months` months."""
    client = get_client()
    log.info("Pulling %dmo hourly bars for %s", months, symbol)

    raw = client.get_price_history(
        symbol=symbol,
        period_type="month",
        period=min(months, 6),
        frequency_type="minute",
        frequency=60,
        need_extended_hours=False,
    )
    return _parse_bars(raw, symbol, "1h")


def collect_5min_bars(symbol: str, days: int = 10) -> list[dict]:
    """
    Pull 5-minute bars. Schwab limits intraday history to 10 days per request.
    For backfill beyond 10 days use collect_5min_bars_chunked().
    """
    client = get_client()
    log.info("Pulling %dd 5m bars for %s", days, symbol)

    raw = client.get_price_history(
        symbol=symbol,
        period_type="day",
        period=min(days, 10),
        frequency_type="minute",
        frequency=5,
        need_extended_hours=False,
    )
    return _parse_bars(raw, symbol, "5m")


def collect_5min_bars_chunked(symbol: str, total_days: int = 90) -> list[dict]:
    """
    Pull 5-minute bars going back up to total_days by requesting 10-day
    chunks and concatenating. Used for initial historical backfill only.
    Deduplication is handled by QuestDB's timestamp partitioning.
    """
    import time
    from datetime import date, timedelta

    all_bars: list[dict] = []
    client = get_client()

    chunk_size = 10
    chunks = (total_days + chunk_size - 1) // chunk_size

    end_date = date.today() - timedelta(days=1)
    for i in range(chunks):
        chunk_end   = end_date - timedelta(days=i * chunk_size)
        chunk_start = chunk_end - timedelta(days=chunk_size - 1)
        log.info("5m chunk %d/%d for %s: %s → %s",
                 i + 1, chunks, symbol, chunk_start, chunk_end)
        raw = client.get_price_history(
            symbol=symbol,
            period_type="day",
            period=chunk_size,
            frequency_type="minute",
            frequency=5,
            start_datetime=datetime(chunk_start.year, chunk_start.month, chunk_start.day,
                                   tzinfo=timezone.utc),
            end_datetime=datetime(chunk_end.year, chunk_end.month, chunk_end.day,
                                 23, 59, tzinfo=timezone.utc),
            need_extended_hours=False,
        )
        all_bars.extend(_parse_bars(raw, symbol, "5m"))
        time.sleep(0.7)   # rate limit headroom

    log.info("5m chunked: %d total bars for %s", len(all_bars), symbol)
    return all_bars


def collect_1min_bars(symbol: str, days: int = 10) -> list[dict]:
    """
    Pull 1-minute bars. Schwab limits intraday history to 10 days per request.
    Collect daily at EOD — too high volume to write intraday.
    """
    client = get_client()
    log.info("Pulling %dd 1m bars for %s", days, symbol)

    raw = client.get_price_history(
        symbol=symbol,
        period_type="day",
        period=min(days, 10),
        frequency_type="minute",
        frequency=1,
        need_extended_hours=False,
    )
    return _parse_bars(raw, symbol, "1m")


def _parse_bars(raw: dict, symbol: str, bar_size: str) -> list[dict]:
    candles = raw.get("candles", [])
    rows = []
    for c in candles:
        ts_ms = c.get("datetime")
        if ts_ms is None:
            continue
        ts = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
        rows.append({
            "ts":      ts,
            "symbol":  symbol,
            "bar_size": bar_size,
            "open":    float(c.get("open",   0)),
            "high":    float(c.get("high",   0)),
            "low":     float(c.get("low",    0)),
            "close":   float(c.get("close",  0)),
            "volume":  int(c.get("volume",   0)),
        })
    log.info("  → %d bars parsed for %s (%s)", len(rows), symbol, bar_size)
    return rows


def collect_vix() -> list[dict]:
    """Pull VIX history (uses $VIX.X ticker on Schwab)."""
    return collect_daily_ohlcv("$VIX.X", years=2)
