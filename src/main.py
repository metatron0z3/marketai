import psycopg2
from config import Config
import time


def connect_to_questdb():
    """Connect to QuestDB using psycopg2."""
    attempts = 5
    delay = 5  # seconds
    for attempt in range(attempts):
        try:
            conn = psycopg2.connect(
                host=Config.QUESTDB_HOST,
                port=Config.QUESTDB_PORT,
                user=Config.QUESTDB_USER,
                password=Config.QUESTDB_PASSWORD,
                dbname=Config.QUESTDB_DATABASE,
            )
            return conn
        except psycopg2.OperationalError as e:
            print(f"Database connection error: {e}")
            raise
        except psycopg2.ProgrammingError as e:
            print(f"SQL error: {e}")
            raise


def create_table(conn):
    """Create a sample table in QuestDB."""
    with conn.cursor() as cursor:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sensor_data (
                timestamp TIMESTAMP,
                sensor_id INT,
                value DOUBLE
            ) TIMESTAMP(timestamp) PARTITION BY DAY;
        """)
        conn.commit()


def insert_data(conn):
    """Insert sample data into the table."""
    with conn.cursor() as cursor:
        cursor.execute("""
            INSERT INTO sensor_data (timestamp, sensor_id, value)
            VALUES (now(), 1, 42.5);
        """)
        conn.commit()


def main():
    """Main function to run the app."""
    conn = connect_to_questdb()
    try:
        create_table(conn)
        insert_data(conn)
        print("Table created and data inserted successfully.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
