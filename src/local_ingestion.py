import databento as db
import pandas as pd
from config import Config
import os
import tempfile
import zstd
import logging
import time
import socket
import subprocess
import os
import requests
import json
import zstandard as zstd

# try:
#     import psycopg2
#     from psycopg2 import OperationalError
# except ImportError:
#     # Fallback if psycopg2 not available locally
#     psycopg2 = None
#     OperationalError = Exception

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


def execute_query(query):
    """Execute a query using QuestDB's HTTP interface"""
    try:
        # Use GET request with query parameter
        response = requests.get("http://questdb:9000/exec", params={"query": query})
        response.raise_for_status()
        result = response.json()

        # Check if query was successful
        if "error" in result:
            print(f"Query error: {result['error']}")
            return None

        return result
    except requests.exceptions.RequestException as e:
        print(f"Error executing query: {e}")
        return None


def wait_for_questdb(host, port=9000, max_attempts=30):
    """Wait for QuestDB HTTP interface using actual HTTP requests"""
    import time

    for attempt in range(1, max_attempts + 1):
        try:
            print(f"Waiting for QuestDB at {host}:{port}...")
            sock = socket.create_connection((host, port), timeout=5)
            sock.close()
            print(f"✓ QuestDB is ready! (attempt {attempt})")
            return True
        except (socket.error, ConnectionRefusedError) as e:  # Removed OperationalError
            print(f"Attempt {attempt}/{max_attempts}: {e}")
            if attempt < max_attempts:
                time.sleep(2)
            else:
                print(f"Failed to connect to QuestDB after {max_attempts} attempts")
                return False
    return False


def test_questdb_connection():
    """Test QuestDB HTTP connection"""
    result = execute_query("SELECT 1")
    if result and "error" not in result:
        print("✓ QuestDB HTTP connection successful")
        return True
    else:
        print("✗ QuestDB HTTP connection failed")
        return False


def create_table_if_not_exists():
    """Create the table using HTTP interface"""
    create_table_query = """
    CREATE TABLE IF NOT EXISTS trades_data (
        ts_recv TIMESTAMP,
        ts_event TIMESTAMP,
        rtype INT,
        publisher_id INT,
        instrument_id INT,
        action SYMBOL,
        side SYMBOL,
        depth INT,
        price DOUBLE,
        size LONG,
        flags INT,
        ts_in_delta LONG,
        sequence LONG
    ) TIMESTAMP(ts_event) PARTITION BY DAY;
    """

    result = execute_query(create_table_query)
    if result:
        print("Table created/verified successfully")
        return True
    else:
        print("Failed to create table")
        return False


def insert_data(data_rows):
    """Insert TBBO data into QuestDB."""

    insert_query = "INSERT INTO tbbo_data (ts_recv, ts_event, rtype, publisher_id, instrument_id,action, side, depth, price, size, flags, ts_in_delta,sequence, bid_px_00, ask_px_00, bid_sz_00, ask_sz_00, bid_ct_00, ask_ct_00, symbol) VALUES "

    values = []

    for row in data_rows:
        # Format timestamp properly for QuestDB
        timestamp = row["ts_recv"]
        if isinstance(timestamp, (int, float)):
            # Convert nanoseconds to timestamp
            timestamp = f"to_timestamp({timestamp})"
        else:
            timestamp = f"'{timestamp}'"

        values.append(
            f"('{row['ts_recv']}', '{row['ts_event']}', '{row['rtype']}', '{row['publisher_id']}', '{row['instrument_id']}', '{row['action']}', '{row['side']}', '{row['depth']}', '{row['price']}', '{row['size']}', '{row['flags']}', '{row['ts_in_delta']}', '{row['sequence']}', '{row['bid_px_00']}', '{row['ask_px_00']}', '{row['bid_sz_00']}', '{row['ask_sz_00']}', '{row['bid_ct_00']}', '{row['ask_ct_00']}', '{row['symbol']}')"
        )

    insert_query += ", ".join(values)

    result = execute_query(insert_query)
    return result is not None

    # pd.Timestamp(row["ts_recv"]).to_pydatetime()
    # if pd.notnull(row["ts_recv"])
    # else None,
    # pd.Timestamp(row["ts_event"]).to_pydatetime()
    # if pd.notnull(row["ts_event"])
    # else None,
    # row["rtype"] if pd.notnull(row["rtype"]) else None,
    # row["publisher_id"] if pd.notnull(row["publisher_id"]) else None,
    # row["instrument_id"] if pd.notnull(row["instrument_id"]) else None,
    # row["action"] if pd.notnull(row["action"]) else None,
    # row["side"] if pd.notnull(row["side"]) else None,
    # row["depth"] if pd.notnull(row["depth"]) else None,
    # row["price"] if pd.notnull(row["price"]) else None,
    # row["size"] if pd.notnull(row["size"]) else None,
    # row["flags"] if pd.notnull(row["flags"]) else None,
    # row["ts_in_delta"] if pd.notnull(row["ts_in_delta"]) else None,
    # row["sequence"] if pd.notnull(row["sequence"]) else None,
    # row["bid_px_00"] if pd.notnull(row["bid_px_00"]) else None,
    # row["ask_px_00"] if pd.notnull(row["ask_px_00"]) else None,
    # row["bid_sz_00"] if pd.notnull(row["bid_sz_00"]) else None,
    # row["ask_sz_00"] if pd.notnull(row["ask_sz_00"]) else None,
    # row["bid_ct_00"] if pd.notnull(row["bid_ct_00"]) else None,
    # row["ask_ct_00"] if pd.notnull(row["ask_ct_00"]) else None,
    # row["symbol"] if pd.notnull(row["symbol"]) else None,


def decompress_zst(input_path, output_path):
    """Decompress .zst file using system zstd command"""
    try:
        result = subprocess.run(
            ["zstd", "-d", input_path, "-o", output_path],
            capture_output=True,
            text=True,
            check=True,
        )
        print(f"Successfully decompressed {input_path} to {output_path}")
    except subprocess.CalledProcessError as e:
        raise Exception(f"Failed to decompress {input_path}: {e.stderr}")


def process_single_tbbo_file(zst_path):
    if not os.path.exists(zst_path):
        raise FileNotFoundError(f"File not found: {zst_path}")

    print(f"Processing single .dbn.zst file: {zst_path}")
    print(f"File size: {os.path.getsize(zst_path)} bytes")

    # Create table if it doesn't exist (no connection parameter needed)
    if not create_table_if_not_exists():
        print("Failed to create table. Exiting.")
        return

    # Your existing file processing logic here...
    try:
        import databento as db

        print("Opening DBN file...")
        # Use the correct way to read DBN files
        store = db.DBNStore.from_file(zst_path)

        print("DBN file opened successfully")

        records = []
        batch_size = 1000
        total_processed = 0

        print("Starting to read records...")
        for i, record in enumerate(store):
            # Log first few records to see structure
            if i < 3:
                print(f"Record {i}: type={type(record)}")
                print(
                    f"Record {i} fields: {[attr for attr in dir(record) if not attr.startswith('_')]}"
                )
                print(f"Record {i} sample: {record}")

            # You'll need to map the actual record fields to your table columns
            # Based on the first few records, adjust the field mapping
            try:
                record_dict = {
                    "ts_recv": getattr(record, "ts_recv", None),
                    "ts_event": getattr(record, "ts_event", None),
                    "rtype": getattr(record, "rtype", None),
                    "publisher_id": getattr(record, "publisher_id", None),
                    "instrument_id": getattr(record, "instrument_id", None),
                    "action": getattr(record, "action", None),
                    "side": getattr(record, "side", None),
                    "depth": getattr(record, "depth", None),
                    "price": getattr(record, "price", None),
                    "size": getattr(record, "size", None),
                    "flags": getattr(record, "flags", None),
                    "ts_in_delta": getattr(record, "ts_in_delta", None),
                    "sequence": getattr(record, "sequence", None),
                    "bid_px_00": getattr(record, "bid_px_00", None),
                    "ask_px_00": getattr(record, "ask_px_00", None),
                    "bid_sz_00": getattr(record, "bid_sz_00", None),
                    "ask_sz_00": getattr(record, "ask_sz_00", None),
                    "bid_ct_00": getattr(record, "bid_ct_00", None),
                    "ask_ct_00": getattr(record, "ask_ct_00", None),
                    "symbol": getattr(record, "symbol", None),
                }

                records.append(record_dict)
                total_processed += 1

                # Process in batches
                if len(records) >= batch_size:
                    print(f"Inserting batch of {len(records)} records")
                    insert_data(records)
                    records = []

                # Break early for testing
                if i >= 10:
                    print(f"Breaking early for testing (processed {i + 1} records)")
                    break

            except Exception as e:
                print(f"Error processing record {i}: {e}")
                break

        # Insert remaining records
        if records:
            print(f"Inserting final batch of {len(records)} records")
            insert_data(records)

        print(f"COMPLETED! Total records processed: {total_processed}")

        # Close the store
        store.close()

    except Exception as e:
        print(f"Error processing file: {e}")
        import traceback

        traceback.print_exc()


def main():
    test_file = "/data/test_data/xnas-itch-20240102.trades.dbn.zst"

    # Check HTTP port instead of PostgreSQL port
    if not wait_for_questdb("questdb", 9000):  # Changed to port 9000
        print("QuestDB is not ready. Exiting.")
        return

    process_single_tbbo_file(test_file)


if __name__ == "__main__":
    main()
