"""
Connections to the TOS MCP server's databases.

The TOS MCP server owns schema creation and all writes.
MarketAI is read-only from these connections.

Environment variables:
  TOS_QUESTDB_HOST     host of TOS QuestDB (default: tos-questdb)
  TOS_QUESTDB_PORT     PG wire port        (default: 9100)
  TOS_POSTGRES_HOST    host of TOS Postgres (default: tos-postgres)
  TOS_POSTGRES_PORT                         (default: 5433)
  TOS_POSTGRES_DB                           (default: tos)
  TOS_POSTGRES_USER                         (default: tos_reader)
  TOS_POSTGRES_PASS                         (default: tos_reader)
"""
import os

import psycopg2
import psycopg2.extras


def get_tos_questdb() -> psycopg2.extensions.connection:
    """Read-only QuestDB connection to TOS time-series data."""
    return psycopg2.connect(
        host=os.getenv("TOS_QUESTDB_HOST", "tos-questdb"),
        port=int(os.getenv("TOS_QUESTDB_PORT", "9100")),
        database="qdb",
        user="admin",
        password=os.getenv("TOS_QUESTDB_PASS", "quest"),
    )


def get_tos_postgres() -> psycopg2.extensions.connection:
    """Read-only Postgres connection to TOS reference/signal data."""
    return psycopg2.connect(
        host=os.getenv("TOS_POSTGRES_HOST", "tos-postgres"),
        port=int(os.getenv("TOS_POSTGRES_PORT", "5433")),
        database=os.getenv("TOS_POSTGRES_DB", "tos"),
        user=os.getenv("TOS_POSTGRES_USER", "tos_reader"),
        password=os.getenv("TOS_POSTGRES_PASS", "tos_reader"),
        cursor_factory=psycopg2.extras.RealDictCursor,
    )


def tos_available() -> bool:
    """Quick liveness check — returns False if TOS MCP server is unreachable."""
    try:
        conn = get_tos_postgres()
        cur = conn.cursor()
        cur.execute("SELECT 1")
        cur.close()
        conn.close()
        return True
    except Exception:
        return False
