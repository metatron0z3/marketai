"""
Tests for the data_source parameter on generate_labels and generate_whale_labels.

Verifies that 'massive' routes the equity price query to underlying_bars and
'databento' routes it to trades_data — without touching a live database.
"""

from unittest.mock import MagicMock, call, patch

import pandas as pd
import pytest

from app.modules.options.services.labels import generate_labels
from app.modules.options.services.whale_labels import generate_whale_labels


def _make_conn(feature_rows, price_rows):
    """Return a mock connection whose cursor returns feature_rows then price_rows."""
    conn = MagicMock()
    cur = MagicMock()
    cur.fetchall.side_effect = [feature_rows, price_rows]
    conn.cursor.return_value = cur
    return conn, cur


# Shared test data
_FEATURE_ROW = [("2026-01-15 09:30:00", "SPY")]
_PRICE_ROW_NOW = [("2026-01-15 09:30:00", 580.0)]
_PRICE_ROW_FUTURE = [("2026-01-16 09:30:00", 600.0)]  # >2% move


class TestGenerateLabelsDataSource:
    def test_massive_queries_underlying_bars(self):
        conn, cur = _make_conn(_FEATURE_ROW, _PRICE_ROW_NOW + _PRICE_ROW_FUTURE)
        with patch("app.modules.options.services.labels.get_db_connection", return_value=conn):
            generate_labels("SPY", "2026-01-01", "2026-01-31", data_source="massive")

        calls = [str(c) for c in cur.execute.call_args_list]
        assert any("underlying_bars" in c for c in calls), \
            "Expected query against underlying_bars for data_source='massive'"
        assert not any("trades_data" in c for c in calls), \
            "trades_data must not be queried when data_source='massive'"

    def test_databento_queries_trades_data(self):
        conn, cur = _make_conn(_FEATURE_ROW, _PRICE_ROW_NOW + _PRICE_ROW_FUTURE)
        with patch("app.modules.options.services.labels.get_db_connection", return_value=conn):
            generate_labels("SPY", "2026-01-01", "2026-01-31", data_source="databento")

        calls = [str(c) for c in cur.execute.call_args_list]
        assert any("trades_data" in c for c in calls), \
            "Expected query against trades_data for data_source='databento'"
        assert not any("underlying_bars" in c for c in calls), \
            "underlying_bars must not be queried when data_source='databento'"

    def test_default_is_databento(self):
        conn, cur = _make_conn(_FEATURE_ROW, _PRICE_ROW_NOW + _PRICE_ROW_FUTURE)
        with patch("app.modules.options.services.labels.get_db_connection", return_value=conn):
            generate_labels("SPY", "2026-01-01", "2026-01-31")

        calls = [str(c) for c in cur.execute.call_args_list]
        assert any("trades_data" in c for c in calls)

    def test_no_feature_rows_returns_zero(self):
        conn, cur = _make_conn([], [])
        with patch("app.modules.options.services.labels.get_db_connection", return_value=conn):
            result = generate_labels("SPY", "2026-01-01", "2026-01-31", data_source="massive")
        assert result == 0

    def test_no_price_rows_returns_zero(self):
        conn, cur = _make_conn(_FEATURE_ROW, [])
        with patch("app.modules.options.services.labels.get_db_connection", return_value=conn):
            result = generate_labels("SPY", "2026-01-01", "2026-01-31", data_source="massive")
        assert result == 0


class TestGenerateWhaleLabelsDataSource:
    def test_massive_queries_underlying_bars(self):
        conn, cur = _make_conn(_FEATURE_ROW, _PRICE_ROW_NOW + _PRICE_ROW_FUTURE)
        with patch("app.modules.options.services.whale_labels.get_db_connection", return_value=conn):
            generate_whale_labels("SPY", "2026-01-01", "2026-01-31", data_source="massive")

        calls = [str(c) for c in cur.execute.call_args_list]
        assert any("underlying_bars" in c for c in calls), \
            "Expected query against underlying_bars for data_source='massive'"
        assert not any("trades_data" in c for c in calls)

    def test_databento_queries_trades_data(self):
        conn, cur = _make_conn(_FEATURE_ROW, _PRICE_ROW_NOW + _PRICE_ROW_FUTURE)
        with patch("app.modules.options.services.whale_labels.get_db_connection", return_value=conn):
            generate_whale_labels("SPY", "2026-01-01", "2026-01-31", data_source="databento")

        calls = [str(c) for c in cur.execute.call_args_list]
        assert any("trades_data" in c for c in calls)
        assert not any("underlying_bars" in c for c in calls)

    def test_default_is_databento(self):
        conn, cur = _make_conn(_FEATURE_ROW, _PRICE_ROW_NOW + _PRICE_ROW_FUTURE)
        with patch("app.modules.options.services.whale_labels.get_db_connection", return_value=conn):
            generate_whale_labels("SPY", "2026-01-01", "2026-01-31")

        calls = [str(c) for c in cur.execute.call_args_list]
        assert any("trades_data" in c for c in calls)

    def test_no_feature_rows_returns_zero(self):
        conn, cur = _make_conn([], [])
        with patch("app.modules.options.services.whale_labels.get_db_connection", return_value=conn):
            result = generate_whale_labels("SPY", "2026-01-01", "2026-01-31", data_source="massive")
        assert result == 0
