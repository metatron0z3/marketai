import pytest
from src.main import connect_to_questdb


def test_connect_to_questdb():
    try:
        conn = connect_to_questdb()
        conn.close()
        assert True
    except Exception:
        pytest.fail("Failed to connect to QuestDB")
