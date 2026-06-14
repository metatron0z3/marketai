"""
Tests for the data_source parameter on compute_features and compute_whale_features.

Verifies that 'massive' routes queries to options_bars / underlying_bars and
'databento' routes them to options_trades / trades_data — without a live database.
"""

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from app.modules.options.services.features import compute_features
from app.modules.options.services.whale_features import compute_whale_features


def _make_conn(*fetchall_returns):
    """Return a mock connection whose cursor returns each value in sequence."""
    conn = MagicMock()
    cur = MagicMock()
    cur.fetchall.side_effect = list(fetchall_returns)
    conn.cursor.return_value = cur
    return conn, cur


# ---------------------------------------------------------------------------
# Fixture data for compute_features (options_bars: 10 cols, options_trades: 19 cols)
# ---------------------------------------------------------------------------

_FEATURES_BAR_ROW = (
    "2026-01-15 09:30:00",  # ts_event
    "SPY",                  # underlying_symbol (aliased to symbol)
    550.0,                  # strike_price (aliased to strike)
    date(2026, 2, 21),      # expiration_date (aliased to expiration)
    "C",                    # contract_type (aliased to put_call)
    5.10,                   # open
    5.50,                   # high
    4.90,                   # low
    5.20,                   # close
    100,                    # volume
)

_FEATURES_TRADE_ROW = (
    "2026-01-15 09:30:00",  # ts_event
    "SPY",                  # symbol
    550.0,                  # strike
    date(2026, 2, 21),      # expiration
    "C",                    # put_call
    5.20,                   # price
    10,                     # size
    5.10,                   # bid
    5.30,                   # ask
    "CBOE",                 # exchange
    0.25,                   # iv
    0.45,                   # delta
    0.01,                   # gamma
    0.05,                   # vega
    -0.03,                  # theta
    1000,                   # open_interest
    "BUY",                  # aggressor_side
    False,                  # is_sweep
    5200.0,                 # premium
)

# ---------------------------------------------------------------------------
# Fixture data for compute_whale_features
# options_bars query: 8 cols (ts_event, symbol, strike, expiration, put_call, close, volume, transactions)
# options_trades query: 11 cols (ts_event, symbol, strike, expiration, put_call, price, size, premium, delta, iv, open_interest)
# Expiration chosen so DTE ~ 30 days when date.today() is patched to 2026-05-22.
# ---------------------------------------------------------------------------

_TODAY_PATCH = date(2026, 5, 22)
_WHALE_EXP = date(2026, 6, 21)  # DTE = 30 days, within [14, 60]

_WHALE_BAR_ROW = (
    "2026-05-15 09:30:00",  # ts_event
    "SPY",                  # underlying_symbol (aliased to symbol)
    550.0,                  # strike_price (aliased to strike)
    _WHALE_EXP,             # expiration_date (aliased to expiration)
    "C",                    # contract_type (aliased to put_call)
    5.20,                   # close  → premium proxy = 5.20 * 100 * 100 = 52000 ≥ 25000
    100,                    # volume
    10,                     # transactions
)

_WHALE_TRADE_ROW = (
    "2026-05-15 09:30:00",  # ts_event
    "SPY",                  # symbol
    550.0,                  # strike
    _WHALE_EXP,             # expiration
    "C",                    # put_call
    5.20,                   # price
    10,                     # size
    52000.0,                # premium  ≥ 25000
    0.45,                   # delta
    0.25,                   # iv
    1000,                   # open_interest
)

_UNDERLYING_BAR_ROW = ("2026-05-15 09:30:00", 580.0)  # ts_event, eq_price


class TestComputeFeaturesDataSource:
    def test_massive_queries_options_bars(self):
        conn, cur = _make_conn([_FEATURES_BAR_ROW])
        with patch("app.modules.options.services.features.get_db_connection", return_value=conn):
            compute_features("SPY", "2026-01-01", "2026-01-31", data_source="massive")

        calls = [str(c) for c in cur.execute.call_args_list]
        assert any("options_bars" in c for c in calls), \
            "Expected query against options_bars for data_source='massive'"
        assert not any("options_trades" in c for c in calls), \
            "options_trades must not be queried when data_source='massive'"

    def test_databento_queries_options_trades(self):
        conn, cur = _make_conn([_FEATURES_TRADE_ROW])
        with patch("app.modules.options.services.features.get_db_connection", return_value=conn):
            compute_features("SPY", "2026-01-01", "2026-01-31", data_source="databento")

        calls = [str(c) for c in cur.execute.call_args_list]
        assert any("options_trades" in c for c in calls), \
            "Expected query against options_trades for data_source='databento'"
        assert not any("options_bars" in c for c in calls), \
            "options_bars must not be queried when data_source='databento'"

    def test_default_is_databento(self):
        conn, cur = _make_conn([_FEATURES_TRADE_ROW])
        with patch("app.modules.options.services.features.get_db_connection", return_value=conn):
            compute_features("SPY", "2026-01-01", "2026-01-31")

        calls = [str(c) for c in cur.execute.call_args_list]
        assert any("options_trades" in c for c in calls)

    def test_no_rows_returns_zero(self):
        conn, cur = _make_conn([])
        with patch("app.modules.options.services.features.get_db_connection", return_value=conn):
            result = compute_features("SPY", "2026-01-01", "2026-01-31", data_source="massive")
        assert result == 0

    def test_massive_returns_row_count(self):
        conn, cur = _make_conn([_FEATURES_BAR_ROW])
        with patch("app.modules.options.services.features.get_db_connection", return_value=conn):
            result = compute_features("SPY", "2026-01-01", "2026-01-31", data_source="massive")
        assert result == 1

    def test_massive_zero_fills_tick_features(self):
        """Verify insert args have 0.0 for sweep_intensity and aggressor_ratio in massive path."""
        conn, cur = _make_conn([_FEATURES_BAR_ROW])
        with patch("app.modules.options.services.features.get_db_connection", return_value=conn):
            compute_features("SPY", "2026-01-01", "2026-01-31", data_source="massive")

        # executemany is called once for the INSERT; grab its args
        assert cur.executemany.called
        _, insert_rows = cur.executemany.call_args[0]
        row = insert_rows[0]
        # Tuple order: ts_event, symbol, strike, expiration, put_call,
        #              rvol, vol_oi_ratio, premium_flow, sweep_intensity, aggressor_ratio,
        #              delta_exposure, iv_rank, days_to_exp, label_24h
        sweep_intensity = row[8]
        aggressor_ratio = row[9]
        delta_exposure = row[10]
        iv_rank = row[11]
        assert sweep_intensity == 0.0
        assert aggressor_ratio == 0.0
        assert delta_exposure == 0.0
        assert iv_rank == 0.0


class TestComputeWhaleFeaturesDataSource:
    # date.today() is patched to _TODAY_PATCH so DTE for _WHALE_EXP is always 30 days (in [14,60]).
    # This ensures the DTE filter passes and the equity enrichment query is always reached.

    def test_massive_queries_options_bars(self):
        conn, cur = _make_conn([_WHALE_BAR_ROW], [_UNDERLYING_BAR_ROW])
        with patch("app.modules.options.services.whale_features.get_db_connection", return_value=conn), \
             patch("app.modules.options.services.whale_features._today", return_value=_TODAY_PATCH):
            compute_whale_features("SPY", "2026-05-01", "2026-05-31", data_source="massive")

        calls = [str(c) for c in cur.execute.call_args_list]
        assert any("options_bars" in c for c in calls), \
            "Expected query against options_bars for data_source='massive'"
        assert not any("options_trades" in c for c in calls), \
            "options_trades must not be queried when data_source='massive'"

    def test_massive_equity_queries_underlying_bars(self):
        conn, cur = _make_conn([_WHALE_BAR_ROW], [_UNDERLYING_BAR_ROW])
        with patch("app.modules.options.services.whale_features.get_db_connection", return_value=conn), \
             patch("app.modules.options.services.whale_features._today", return_value=_TODAY_PATCH):
            compute_whale_features("SPY", "2026-05-01", "2026-05-31", data_source="massive")

        calls = [str(c) for c in cur.execute.call_args_list]
        assert any("underlying_bars" in c for c in calls), \
            "Expected equity price query against underlying_bars for data_source='massive'"
        assert not any("trades_data" in c for c in calls), \
            "trades_data must not be queried when data_source='massive'"

    def test_databento_queries_options_trades(self):
        conn, cur = _make_conn([_WHALE_TRADE_ROW], [_UNDERLYING_BAR_ROW])
        with patch("app.modules.options.services.whale_features.get_db_connection", return_value=conn), \
             patch("app.modules.options.services.whale_features._today", return_value=_TODAY_PATCH):
            compute_whale_features("SPY", "2026-05-01", "2026-05-31", data_source="databento")

        calls = [str(c) for c in cur.execute.call_args_list]
        assert any("options_trades" in c for c in calls), \
            "Expected query against options_trades for data_source='databento'"
        assert not any("options_bars" in c for c in calls), \
            "options_bars must not be queried when data_source='databento'"

    def test_databento_equity_queries_trades_data(self):
        conn, cur = _make_conn([_WHALE_TRADE_ROW], [_UNDERLYING_BAR_ROW])
        with patch("app.modules.options.services.whale_features.get_db_connection", return_value=conn), \
             patch("app.modules.options.services.whale_features._today", return_value=_TODAY_PATCH):
            compute_whale_features("SPY", "2026-05-01", "2026-05-31", data_source="databento")

        calls = [str(c) for c in cur.execute.call_args_list]
        assert any("trades_data" in c for c in calls), \
            "Expected equity price query against trades_data for data_source='databento'"

    def test_default_is_databento(self):
        conn, cur = _make_conn([_WHALE_TRADE_ROW], [_UNDERLYING_BAR_ROW])
        with patch("app.modules.options.services.whale_features.get_db_connection", return_value=conn), \
             patch("app.modules.options.services.whale_features._today", return_value=_TODAY_PATCH):
            compute_whale_features("SPY", "2026-05-01", "2026-05-31")

        calls = [str(c) for c in cur.execute.call_args_list]
        assert any("options_trades" in c for c in calls)

    def test_no_rows_returns_zero(self):
        conn, cur = _make_conn([])
        with patch("app.modules.options.services.whale_features.get_db_connection", return_value=conn):
            result = compute_whale_features("SPY", "2026-05-01", "2026-05-31", data_source="massive")
        assert result == 0
