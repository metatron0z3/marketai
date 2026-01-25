import psycopg2
import os

def get_db_connection():
    """Create database connection to QuestDB"""
    db_host = os.getenv("QUESTDB_HOST", "questdb")
    conn = psycopg2.connect(
        host=db_host,
        port=8812,
        database="questdb",
        user="admin",
        password="quest"
    )
    return conn
