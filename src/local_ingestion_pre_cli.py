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

    try:
        response = requests.get(
            "http://questdb:9000/exec", params={"query": create_table_query}
        )
        if response.status_code == 200:
            print("✅ Trades table created/verified successfully")
            return True
        else:
            print(
                f"❌ Failed to create table: {response.status_code} - {response.text}"
            )
            return False
    except Exception as e:
        print(f"❌ Error creating table: {e}")
        return False


def insert_data(records):
    """Insert trades data with proper formatting"""
    if not records:
        print("⚠️  No records to insert")
        return

    print(f"📝 Preparing to insert {len(records)} trade records...")

    # Build the INSERT statement for trades table
    values_list = []
    for record in records:
        # Format values properly - no quotes around numbers, quotes around strings
        values = f"({record['ts_recv']}, {record['ts_event']}, {record['rtype']}, {record['publisher_id']}, {record['instrument_id']}, '{record['action']}', '{record['side']}', {record['depth']}, {record['price']}, {record['size']}, {record['flags']}, {record['ts_in_delta']}, {record['sequence']})"
        values_list.append(values)

    query = f"""
    INSERT INTO trades_data (ts_recv, ts_event, rtype, publisher_id, instrument_id, action, side, depth, price, size, flags, ts_in_delta, sequence)
    VALUES {", ".join(values_list)}
    """

    try:
        response = requests.get("http://questdb:9000/exec", params={"query": query})

        if response.status_code == 200:
            print(f"✅ Successfully inserted {len(records)} trade records")
        else:
            print(f"❌ Insert failed: {response.status_code}")
            print(f"Response: {response.text}")
            # Print first part of query for debugging
            print(f"Query start: {query[:200]}...")

    except Exception as e:
        print(f"❌ Insert error: {e}")
        raise


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


def process_all_trades_files(trades_folder):
    """Process all .dbn.zst trade files in the specified folder"""
    import glob

    # Find all .dbn.zst files in the trades folder
    pattern = os.path.join(trades_folder, "*.trades.dbn.zst")
    trade_files = glob.glob(pattern)

    if not trade_files:
        print(f"No trade files found in {trades_folder}")
        return

    # Sort files to process them in order
    trade_files.sort()

    print(f"Found {len(trade_files)} trade files to process")

    # Create table once before processing all files
    if not create_table_if_not_exists():
        print("Failed to create table. Exiting.")
        return

    total_files_processed = 0
    total_records_processed = 0

    for file_path in trade_files:
        print(f"\n{'=' * 60}")
        print(
            f"Processing file {total_files_processed + 1}/{len(trade_files)}: {os.path.basename(file_path)}"
        )
        print(f"{'=' * 60}")

        try:
            records_processed = process_single_trades_file_full(file_path)
            total_records_processed += records_processed
            total_files_processed += 1

            print(f"✅ File completed: {records_processed} records processed")

        except Exception as e:
            print(f"❌ Error processing {file_path}: {e}")
            print("Continuing with next file...")
            continue

    print(f"\n🎉 BATCH PROCESSING COMPLETE!")
    print(f"📊 Files processed: {total_files_processed}/{len(trade_files)}")
    print(f"📊 Total records processed: {total_records_processed}")


def process_single_trades_file_full(zst_path):
    """Process a single trade file without early break - returns record count"""
    if not os.path.exists(zst_path):
        raise FileNotFoundError(f"File not found: {zst_path}")

    print(f"Processing trades file: {zst_path}")
    print(f"File size: {os.path.getsize(zst_path)} bytes")

    try:
        import databento as db

        print("Opening DBN file...")
        store = db.DBNStore.from_file(zst_path)
        print("DBN file opened successfully")

        records = []
        batch_size = 50
        total_processed = 0

        print("Starting to read records...")
        for i, record in enumerate(store):
            # Log progress every 10,000 records
            if i % 10000 == 0 and i > 0:
                print(f"📊 Processed {i} records...")

            try:
                record_dict = {
                    "ts_recv": record.ts_recv
                    // 1000,  # Convert nanoseconds to microseconds
                    "ts_event": record.ts_event
                    // 1000,  # Convert nanoseconds to microseconds
                    "rtype": record.rtype,
                    "publisher_id": record.publisher_id,
                    "instrument_id": record.instrument_id,
                    "action": record.action,
                    "side": record.side,
                    "depth": record.depth,
                    "price": record.price
                    / 1000000000,  # Convert from nano-price to regular price
                    "size": record.size,
                    "flags": record.flags,
                    "ts_in_delta": record.ts_in_delta,
                    "sequence": record.sequence,
                }

                records.append(record_dict)
                total_processed += 1

                # Process in batches
                if len(records) >= batch_size:
                    insert_data(records)
                    records = []

            except Exception as e:
                print(f"❌ Error processing record {i}: {e}")
                break

        # Insert remaining records
        if records:
            print(f"📝 Inserting final batch of {len(records)} records")
            insert_data(records)

        print(f"✅ File processing completed: {total_processed} records")

        # Clean up
        del store
        return total_processed

    except Exception as e:
        print(f"❌ Error processing file: {e}")
        import traceback

        traceback.print_exc()
        return 0


def test_trades_data():
    """Test function to verify trades data was inserted"""
    try:
        # Count total records
        response = requests.post(
            "http://questdb:9000/exec",
            params={"query": "SELECT COUNT(*) FROM trades_data"},
        )
        if response.status_code == 200:
            result = response.json()
            count = result["dataset"][0][0]
            print(f"📊 Total trades in database: {count}")

        # Get sample records
        response = requests.post(
            "http://questdb:9000/exec",
            params={"query": "SELECT * FROM trades_data LIMIT 5"},
        )
        if response.status_code == 200:
            result = response.json()
            print(f"📋 Sample records:")
            for row in result["dataset"]:
                print(f"  {row}")

    except Exception as e:
        print(f"❌ Error testing data: {e}")


def main():
    if not wait_for_questdb("questdb", 9000):
        print("QuestDB not available")
        return

    # Process all trade files in the folder
    trades_folder = "/data/trades"
    process_all_trades_files(trades_folder)

    # Test the inserted data
    print("\n" + "=" * 60)
    print("FINAL DATA VERIFICATION")
    print("=" * 60)
    test_trades_data()


if __name__ == "__main__":
    main()
