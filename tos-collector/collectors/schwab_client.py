"""
Schwab API client — rate-limited, OAuth2, with automatic token refresh.

Authentication flow:
  1. First run: schwab-py opens browser for OAuth2 authorization
  2. Token saved to TOS_TOKEN_PATH (default: ~/.tos_token.json)
  3. All subsequent runs load and auto-refresh the token

Environment variables:
  SCHWAB_API_KEY      — your Schwab app key
  SCHWAB_APP_SECRET   — your Schwab app secret
  SCHWAB_CALLBACK_URL — your registered callback URL (default: https://127.0.0.1)
  TOS_TOKEN_PATH      — path to persist OAuth token (default: ~/.tos_token.json)
  TOS_RATE_LIMIT      — requests per minute (default: 100)
"""
import asyncio
import logging
import os
import time
from typing import Any

import schwab

log = logging.getLogger(__name__)

_RATE_LIMIT  = int(os.getenv("TOS_RATE_LIMIT", "100"))   # req/min
_MIN_INTERVAL = 60.0 / _RATE_LIMIT                        # seconds between calls
_TOKEN_PATH  = os.getenv("TOS_TOKEN_PATH", os.path.expanduser("~/.tos_token.json"))


class SchwabClient:
    """
    Thin wrapper around schwab-py that adds:
      - Per-call rate limiting (token bucket)
      - Automatic retry on 429 / 5xx
      - Structured error logging
    """

    def __init__(self):
        self._client: schwab.client.Client | None = None
        self._last_call: float = 0.0

    def connect(self) -> None:
        """
        Build the schwab-py client. First call opens a browser for OAuth2 if no
        token file exists. Subsequent calls load the saved token silently.
        """
        api_key     = os.environ["SCHWAB_API_KEY"]
        app_secret  = os.environ["SCHWAB_APP_SECRET"]
        callback_url = os.getenv("SCHWAB_CALLBACK_URL", "https://127.0.0.1")

        if os.path.exists(_TOKEN_PATH):
            self._client = schwab.auth.client_from_token_file(
                _TOKEN_PATH, api_key, app_secret
            )
            log.info("Loaded Schwab token from %s", _TOKEN_PATH)
        else:
            self._client = schwab.auth.client_from_login_flow(
                api_key, app_secret, callback_url, _TOKEN_PATH
            )
            log.info("Completed OAuth2 login. Token saved to %s", _TOKEN_PATH)

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_call
        if elapsed < _MIN_INTERVAL:
            time.sleep(_MIN_INTERVAL - elapsed)
        self._last_call = time.monotonic()

    def get_chains(
        self,
        symbol: str,
        from_date: str | None = None,
        to_date: str | None = None,
        strike_count: int = 100,
        option_type: schwab.client.Client.Options.Type = schwab.client.Client.Options.Type.ALL,
    ) -> dict:
        """
        Pull full options chain for a symbol.

        from_date / to_date: "YYYY-MM-DD" strings for historical pulls.
        Returns the parsed JSON response dict from Schwab.
        """
        self._throttle()
        assert self._client, "Call connect() first"

        kwargs: dict[str, Any] = {
            "symbol":              symbol,
            "contract_type":       option_type,
            "strike_count":        strike_count,
            "include_underlying_quote": True,
            "strategy":            schwab.client.Client.Options.Strategy.SINGLE,
            "option_type":         schwab.client.Client.Options.Type.ALL,
        }
        if from_date:
            kwargs["from_date"] = from_date
        if to_date:
            kwargs["to_date"] = to_date

        for attempt in range(3):
            resp = self._client.get_chains(**kwargs)
            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code == 429:
                wait = int(resp.headers.get("Retry-After", "10"))
                log.warning("Rate limited on %s — waiting %ds", symbol, wait)
                time.sleep(wait)
            elif resp.status_code in (503, 504):
                log.warning("Schwab 5xx on %s (attempt %d)", symbol, attempt + 1)
                time.sleep(10 * (attempt + 1))
            else:
                log.error("Schwab error %d for %s: %s",
                          resp.status_code, symbol, resp.text[:200])
                resp.raise_for_status()

        raise RuntimeError(f"get_chains failed for {symbol} after 3 attempts")

    def get_price_history(
        self,
        symbol: str,
        period_type: str = "year",
        period: int = 2,
        frequency_type: str = "daily",
        frequency: int = 1,
        start_datetime=None,
        end_datetime=None,
        need_extended_hours: bool = False,
    ) -> dict:
        """Pull OHLCV price history. Returns JSON dict."""
        self._throttle()
        assert self._client

        Client = schwab.client.Client
        period_type_map = {
            "day":   Client.PriceHistory.PeriodType.DAY,
            "month": Client.PriceHistory.PeriodType.MONTH,
            "year":  Client.PriceHistory.PeriodType.YEAR,
            "ytd":   Client.PriceHistory.PeriodType.YEAR_TO_DATE,
        }
        freq_map = {
            "minute": Client.PriceHistory.FrequencyType.MINUTE,
            "daily":  Client.PriceHistory.FrequencyType.DAILY,
            "weekly": Client.PriceHistory.FrequencyType.WEEKLY,
        }
        period_map = {
            ("year",  1): Client.PriceHistory.Period.ONE_YEAR,
            ("year",  2): Client.PriceHistory.Period.TWO_YEARS,
            ("year",  5): Client.PriceHistory.Period.FIVE_YEARS,
            ("month", 1): Client.PriceHistory.Period.ONE_MONTH,
            ("month", 3): Client.PriceHistory.Period.THREE_MONTHS,
            ("month", 6): Client.PriceHistory.Period.SIX_MONTHS,
        }

        kwargs: dict[str, Any] = {
            "symbol":        symbol,
            "period_type":   period_type_map[period_type],
            "frequency_type": freq_map[frequency_type],
            "frequency":     frequency,
            "need_extended_hours_data": need_extended_hours,
        }
        if start_datetime is None and (period_type, period) in period_map:
            kwargs["period"] = period_map[(period_type, period)]
        else:
            kwargs["start_datetime"] = start_datetime
            kwargs["end_datetime"]   = end_datetime

        for attempt in range(3):
            resp = self._client.get_price_history(**kwargs)
            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code == 429:
                time.sleep(int(resp.headers.get("Retry-After", "10")))
            else:
                time.sleep(5 * (attempt + 1))

        raise RuntimeError(f"get_price_history failed for {symbol} after 3 attempts")

    def get_quotes(self, symbols: list[str]) -> dict:
        """Batch quote pull for VIX + underlying context."""
        self._throttle()
        assert self._client
        resp = self._client.get_quotes(symbols)
        resp.raise_for_status()
        return resp.json()


# Module-level singleton
_client: SchwabClient | None = None


def get_client() -> SchwabClient:
    global _client
    if _client is None:
        _client = SchwabClient()
        _client.connect()
    return _client
