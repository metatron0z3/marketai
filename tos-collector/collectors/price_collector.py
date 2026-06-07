"""
Underlying price collector — OHLCV bars from Schwab API.
Populates underlying_intraday_bars in TOS QuestDB.
"""
import logging
from datetime import datetime, timezone

from collectors.schwab_client import get_client

log = logging.getLogger(__name__)

WATCHLIST = [
    "TSLA", "NVDA", "SPY", "QQQ", "AAPL",
    "AMD", "META", "AMZN", "MSFT", "GLD", "TLT", "$VIX.X",
]


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


def collect_1min_bars(symbol: str, days: int = 10) -> list[dict]:
    """Pull 1-minute bars for recent intraday data."""
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
