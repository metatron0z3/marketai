"""
Tests for the Massive REST ingest path.

All network calls and DB connections are mocked — no live Massive API or QuestDB required.
"""

import os
from datetime import date, datetime, timezone
from unittest.mock import MagicMock, call, patch

import pytest
import requests as requests_lib
from pydantic import ValidationError

from app.modules.options.api.ingest import MassiveIngestRequest
from app.modules.options.services.massive_ingest import (
    _get_api_key,
    fetch_agg_bars,
    fetch_contracts,
    write_option_bars,
    write_underlying_bars,
    run_massive_ingest,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_CONTRACT = {
    "ticker": "O:SPY260116C00580000",
    "underlying_ticker": "SPY",
    "contract_type": "call",
    "expiration_date": "2026-01-16",
    "strike_price": 580.0,
    "shares_per_contract": 100,
    "exercise_style": "american",
    "primary_exchange": "BATO",
    "active": True,
    "as_of": "2026-05-22",
}

SAMPLE_BAR = {
    "t": 1748044800000,  # 2026-05-24 00:00:00 UTC (epoch ms)
    "o": 2.5,
    "h": 3.1,
    "l": 2.3,
    "c": 2.9,
    "v": 500,
    "n": 42,
    "vw": 2.7,
}

SAMPLE_BAR_2 = dict(SAMPLE_BAR, t=1748131200000)  # next day


def _mock_conn():
    conn = MagicMock()
    cur = MagicMock()
    cur.fetchall.return_value = []
    conn.cursor.return_value = cur
    return conn, cur


# ---------------------------------------------------------------------------
# API key
# ---------------------------------------------------------------------------

class TestGetApiKey:
    def test_raises_when_missing(self):
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("MASSIVE_API_KEY", None)
            with pytest.raises(ValueError, match="MASSIVE_API_KEY"):
                _get_api_key()

    def test_returns_key(self):
        with patch.dict(os.environ, {"MASSIVE_API_KEY": "secret-key"}):
            assert _get_api_key() == "secret-key"


# ---------------------------------------------------------------------------
# Contract discovery
# ---------------------------------------------------------------------------

class TestFetchContracts:
    def test_single_page_no_pagination(self):
        response = {"results": [SAMPLE_CONTRACT], "next_url": None}
        with patch("app.modules.options.services.massive_ingest._massive_get", return_value=response):
            contracts = fetch_contracts("SPY", "2026-05-22", True, "key")
        assert len(contracts) == 1
        assert contracts[0]["ticker"] == "O:SPY260116C00580000"

    def test_pagination_follows_next_url(self):
        page1 = {
            "results": [SAMPLE_CONTRACT],
            "next_url": "https://api.massive.com/v3/reference/options/contracts?cursor=abc",
        }
        page2 = {
            "results": [dict(SAMPLE_CONTRACT, ticker="O:SPY260116P00580000", contract_type="put")],
            "next_url": None,
        }
        with patch("app.modules.options.services.massive_ingest._massive_get", return_value=page1), \
             patch("app.modules.options.services.massive_ingest._massive_get_url", return_value=page2):
            contracts = fetch_contracts("SPY", "2026-05-22", True, "key")
        assert len(contracts) == 2
        assert contracts[1]["contract_type"] == "put"

    def test_multi_page_pagination(self):
        pages = [
            {"results": [SAMPLE_CONTRACT], "next_url": "https://api.massive.com/next?cursor=p2"},
            {"results": [dict(SAMPLE_CONTRACT, ticker="O:SPY260116P00580000")], "next_url": "https://api.massive.com/next?cursor=p3"},
            {"results": [dict(SAMPLE_CONTRACT, ticker="O:SPY260116C00600000")], "next_url": None},
        ]
        with patch("app.modules.options.services.massive_ingest._massive_get", return_value=pages[0]), \
             patch("app.modules.options.services.massive_ingest._massive_get_url", side_effect=pages[1:]):
            contracts = fetch_contracts("SPY", "2026-05-22", True, "key")
        assert len(contracts) == 3

    def test_empty_results(self):
        response = {"results": [], "next_url": None}
        with patch("app.modules.options.services.massive_ingest._massive_get", return_value=response):
            contracts = fetch_contracts("SPY", "2026-05-22", True, "key")
        assert contracts == []

    def test_contract_metadata_mapping(self):
        """Spot-check that all reference fields survive the round-trip through fetch_contracts."""
        response = {"results": [SAMPLE_CONTRACT], "next_url": None}
        with patch("app.modules.options.services.massive_ingest._massive_get", return_value=response):
            contracts = fetch_contracts("SPY", "2026-05-22", True, "key")
        c = contracts[0]
        assert c["ticker"] == "O:SPY260116C00580000"
        assert c["underlying_ticker"] == "SPY"
        assert c["contract_type"] == "call"
        assert c["expiration_date"] == "2026-01-16"
        assert c["strike_price"] == 580.0
        assert c["shares_per_contract"] == 100
        assert c["exercise_style"] == "american"
        assert c["primary_exchange"] == "BATO"
        assert c["active"] is True


# ---------------------------------------------------------------------------
# Aggregate bar fetch
# ---------------------------------------------------------------------------

class TestFetchAggBars:
    def test_single_page(self):
        response = {"results": [SAMPLE_BAR], "next_url": None}
        with patch("app.modules.options.services.massive_ingest._massive_get", return_value=response):
            bars = fetch_agg_bars("O:SPY260116C00580000", 1, "day", "2026-05-01", "2026-05-22", "key")
        assert len(bars) == 1
        assert bars[0]["o"] == 2.5

    def test_pagination_follows_next_url(self):
        page1 = {"results": [SAMPLE_BAR], "next_url": "https://api.massive.com/next?cursor=x"}
        page2 = {"results": [SAMPLE_BAR_2], "next_url": None}
        with patch("app.modules.options.services.massive_ingest._massive_get", return_value=page1), \
             patch("app.modules.options.services.massive_ingest._massive_get_url", return_value=page2):
            bars = fetch_agg_bars("O:SPY260116C00580000", 1, "day", "2026-05-01", "2026-05-22", "key")
        assert len(bars) == 2
        assert bars[1]["t"] == SAMPLE_BAR_2["t"]

    def test_aggregate_bar_field_mapping(self):
        """All Massive agg response fields must survive fetch_agg_bars unchanged."""
        response = {"results": [SAMPLE_BAR], "next_url": None}
        with patch("app.modules.options.services.massive_ingest._massive_get", return_value=response):
            bars = fetch_agg_bars("O:SPY260116C00580000", 1, "day", "2026-05-01", "2026-05-22", "key")
        b = bars[0]
        assert b["t"] == 1748044800000
        assert b["o"] == 2.5
        assert b["h"] == 3.1
        assert b["l"] == 2.3
        assert b["c"] == 2.9
        assert b["v"] == 500
        assert b["n"] == 42
        assert b["vw"] == 2.7


# ---------------------------------------------------------------------------
# write_option_bars — mapping and idempotency
# ---------------------------------------------------------------------------

class TestWriteOptionBars:
    def test_inserts_bar_with_correct_field_mapping(self):
        conn, cur = _mock_conn()
        written = write_option_bars(
            conn, [SAMPLE_BAR],
            ticker="O:SPY260116C00580000",
            underlying_symbol="SPY",
            expiration_date="2026-01-16",
            strike_price=580.0,
            contract_type="call",
            bar_multiplier=1,
            bar_timespan="day",
            ingest_run_id="run-1",
            existing_ts_ms=set(),
        )
        assert written == 1
        cur.executemany.assert_called_once()
        _sql, rows = cur.executemany.call_args[0]
        row = rows[0]
        ts = row[0]
        assert ts == datetime.fromtimestamp(SAMPLE_BAR["t"] / 1000, tz=timezone.utc)
        assert row[1] == "O:SPY260116C00580000"   # massive_ticker
        assert row[2] == "SPY"                     # underlying_symbol
        assert row[3] == "2026-01-16"              # expiration_date
        assert row[4] == 580.0                     # strike_price
        assert row[5] == "call"                    # contract_type
        assert row[6] == 1                         # bar_multiplier
        assert row[7] == "day"                     # bar_timespan
        assert row[8] == 2.5                       # open
        assert row[9] == 3.1                       # high
        assert row[10] == 2.3                      # low
        assert row[11] == 2.9                      # close
        assert row[12] == 500                      # volume
        assert row[13] == 42                       # transactions
        assert row[14] == 2.7                      # vwap
        assert row[15] == "massive"                # source
        assert row[16] == "run-1"                  # ingest_run_id

    def test_idempotent_skips_existing_timestamp(self):
        conn, cur = _mock_conn()
        existing = {SAMPLE_BAR["t"]}  # same epoch ms already in DB
        written = write_option_bars(
            conn, [SAMPLE_BAR],
            ticker="O:SPY260116C00580000",
            underlying_symbol="SPY",
            expiration_date="2026-01-16",
            strike_price=580.0,
            contract_type="call",
            bar_multiplier=1,
            bar_timespan="day",
            ingest_run_id="run-2",
            existing_ts_ms=existing,
        )
        assert written == 0
        cur.executemany.assert_not_called()

    def test_partial_dedup_writes_only_new_bars(self):
        conn, cur = _mock_conn()
        existing = {SAMPLE_BAR["t"]}  # bar 1 already present
        written = write_option_bars(
            conn, [SAMPLE_BAR, SAMPLE_BAR_2],
            ticker="O:SPY260116C00580000",
            underlying_symbol="SPY",
            expiration_date="2026-01-16",
            strike_price=580.0,
            contract_type="call",
            bar_multiplier=1,
            bar_timespan="day",
            ingest_run_id="run-3",
            existing_ts_ms=existing,
        )
        assert written == 1
        _sql, rows = cur.executemany.call_args[0]
        assert rows[0][0] == datetime.fromtimestamp(SAMPLE_BAR_2["t"] / 1000, tz=timezone.utc)

    def test_empty_bars_returns_zero(self):
        conn, cur = _mock_conn()
        written = write_option_bars(
            conn, [],
            ticker="O:SPY260116C00580000",
            underlying_symbol="SPY",
            expiration_date="2026-01-16",
            strike_price=580.0,
            contract_type="call",
            bar_multiplier=1,
            bar_timespan="day",
            ingest_run_id="run-4",
            existing_ts_ms=set(),
        )
        assert written == 0
        cur.executemany.assert_not_called()

    def test_nullable_fields_when_absent(self):
        conn, cur = _mock_conn()
        bar_no_optionals = {"t": SAMPLE_BAR["t"], "o": 1.0, "h": 1.5, "l": 0.9, "c": 1.2, "v": 100}
        write_option_bars(
            conn, [bar_no_optionals],
            ticker="O:SPY260116C00580000",
            underlying_symbol="SPY",
            expiration_date="2026-01-16",
            strike_price=580.0,
            contract_type="call",
            bar_multiplier=1,
            bar_timespan="day",
            ingest_run_id="run-5",
            existing_ts_ms=set(),
        )
        _sql, rows = cur.executemany.call_args[0]
        row = rows[0]
        assert row[13] is None   # transactions — absent in bar
        assert row[14] is None   # vwap — absent in bar


# ---------------------------------------------------------------------------
# write_underlying_bars — mapping and idempotency
# ---------------------------------------------------------------------------

class TestWriteUnderlyingBars:
    def test_inserts_bar_with_correct_field_mapping(self):
        conn, cur = _mock_conn()
        written = write_underlying_bars(
            conn, [SAMPLE_BAR],
            symbol="SPY",
            bar_multiplier=1,
            bar_timespan="day",
            ingest_run_id="run-1",
            existing_ts_ms=set(),
        )
        assert written == 1
        _sql, rows = cur.executemany.call_args[0]
        row = rows[0]
        assert row[1] == "SPY"     # symbol
        assert row[4] == 2.5       # open
        assert row[5] == 3.1       # high
        assert row[6] == 2.3       # low
        assert row[7] == 2.9       # close
        assert row[8] == 500       # volume
        assert row[11] == "massive"  # source

    def test_idempotent_skips_existing_timestamp(self):
        conn, cur = _mock_conn()
        existing = {SAMPLE_BAR["t"]}
        written = write_underlying_bars(
            conn, [SAMPLE_BAR],
            symbol="SPY",
            bar_multiplier=1,
            bar_timespan="day",
            ingest_run_id="run-2",
            existing_ts_ms=existing,
        )
        assert written == 0
        cur.executemany.assert_not_called()


# ---------------------------------------------------------------------------
# Bounded input validation (Pydantic model)
# ---------------------------------------------------------------------------

class TestMassiveIngestRequest:
    def test_valid_request_defaults(self):
        req = MassiveIngestRequest(
            underlying_symbol="SPY",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 3, 31),
        )
        assert req.bar_timespan == "day"
        assert req.bar_multiplier == 1
        assert req.include_expired is True
        assert req.max_contracts == 100

    def test_end_before_start_raises(self):
        with pytest.raises(ValidationError, match="end_date"):
            MassiveIngestRequest(
                underlying_symbol="SPY",
                start_date=date(2026, 3, 31),
                end_date=date(2026, 1, 1),
            )

    def test_range_exceeds_365_days_raises(self):
        with pytest.raises(ValidationError, match="365"):
            MassiveIngestRequest(
                underlying_symbol="SPY",
                start_date=date(2025, 1, 1),
                end_date=date(2026, 5, 1),
            )

    def test_invalid_timespan_raises(self):
        with pytest.raises(ValidationError):
            MassiveIngestRequest(
                underlying_symbol="SPY",
                start_date=date(2026, 1, 1),
                end_date=date(2026, 3, 31),
                bar_timespan="tick",
            )

    def test_max_contracts_out_of_range_raises(self):
        with pytest.raises(ValidationError):
            MassiveIngestRequest(
                underlying_symbol="SPY",
                start_date=date(2026, 1, 1),
                end_date=date(2026, 3, 31),
                max_contracts=0,
            )

    def test_exactly_365_days_is_valid(self):
        req = MassiveIngestRequest(
            underlying_symbol="AAPL",
            start_date=date(2025, 5, 22),
            end_date=date(2026, 5, 22),
        )
        assert (req.end_date - req.start_date).days == 365


# ---------------------------------------------------------------------------
# Graceful handling of contracts with no bars (404)
# ---------------------------------------------------------------------------

class TestNoBarsBehavior:
    def test_404_on_contract_bars_does_not_abort_ingest(self):
        """A 404 from the agg endpoint for one contract must be skipped, not raise."""
        mock_404 = MagicMock()
        mock_404.status_code = 404
        http_404 = requests_lib.HTTPError(response=mock_404)

        conn, cur = _mock_conn()

        contracts_page = {"results": [SAMPLE_CONTRACT], "next_url": None}
        underlying_page = {"results": [SAMPLE_BAR], "next_url": None}

        with patch("app.modules.options.services.massive_ingest._get_api_key", return_value="key"), \
             patch("app.modules.options.services.massive_ingest.get_db_connection", return_value=conn), \
             patch("app.modules.options.services.massive_ingest.fetch_contracts", return_value=[SAMPLE_CONTRACT]), \
             patch("app.modules.options.services.massive_ingest.write_contracts"), \
             patch(
                 "app.modules.options.services.massive_ingest.fetch_agg_bars",
                 side_effect=[http_404, [SAMPLE_BAR]],   # option ticker 404, underlying succeeds
             ), \
             patch("app.modules.options.services.massive_ingest._write_ingest_run") as mock_write_run:
            run_massive_ingest(
                underlying_symbol="SPY",
                start_date="2026-01-01",
                end_date="2026-03-31",
                bar_timespan="day",
                bar_multiplier=1,
                include_expired=True,
                max_contracts=10,
                ingest_run_id="run-404-test",
            )

        run_arg = mock_write_run.call_args[0][1]
        assert run_arg["status"] == "completed"
        assert run_arg["contracts_ingested"] == 0   # 404 contract was skipped
        assert run_arg["contracts_discovered"] == 1

    def test_non_404_http_error_propagates_to_error_status(self):
        """A 500 from the agg endpoint must be treated as an ingest failure."""
        mock_500 = MagicMock()
        mock_500.status_code = 500
        http_500 = requests_lib.HTTPError(response=mock_500)

        conn, cur = _mock_conn()

        with patch("app.modules.options.services.massive_ingest._get_api_key", return_value="key"), \
             patch("app.modules.options.services.massive_ingest.get_db_connection", return_value=conn), \
             patch("app.modules.options.services.massive_ingest.fetch_contracts", return_value=[SAMPLE_CONTRACT]), \
             patch("app.modules.options.services.massive_ingest.write_contracts"), \
             patch("app.modules.options.services.massive_ingest.fetch_agg_bars", side_effect=http_500), \
             patch("app.modules.options.services.massive_ingest._write_ingest_run") as mock_write_run:
            run_massive_ingest(
                underlying_symbol="SPY",
                start_date="2026-01-01",
                end_date="2026-03-31",
                bar_timespan="day",
                bar_multiplier=1,
                include_expired=True,
                max_contracts=10,
                ingest_run_id="run-500-test",
            )

        run_arg = mock_write_run.call_args[0][1]
        assert run_arg["status"] == "error"
        assert run_arg["error"] is not None
