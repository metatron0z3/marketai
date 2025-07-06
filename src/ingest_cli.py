import argparse
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
import glob
import sys

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


def execute_query(query):
    """Execute a query using QuestDB's HTTP interface"""
    try:
        response = requests.get("http://questdb:9000/exec", params={"query": query})
        response.raise_for_status()
        result = response.json()

        if "error" in result:
            print(f"Query error: {result['error']}")
            return None

        return result
    except requests.exceptions.RequestException as e:
        print(f"Error executing query: {e}")
        return None


def wait_for_questdb(host, port=9000, max_attempts=30):
    """Wait for QuestDB HTTP interface using actual HTTP requests"""
    for attempt in range(1, max_attempts + 1):
        try:
            print(f"Waiting for QuestDB at {host}:{port}...")
            sock = socket.create_connection((host, port), timeout=5)
            sock.close()
            print(f"✓ QuestDB is ready! (attempt {attempt})")
            return True
        except (socket.error, ConnectionRefusedError) as e:
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

    values_list = []
    for record in records:
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

    except Exception as e:
        print(f"❌ Insert error: {e}")
        raise


def process_single_trades_file(zst_path, batch_size=50):
    """Process a single trade file - returns record count"""
    if not os.path.exists(zst_path):
        raise FileNotFoundError(f"File not found: {zst_path}")

    print(f"Processing trades file: {zst_path}")
    print(f"File size: {os.path.getsize(zst_path)} bytes")

    try:
        store = db.DBNStore.from_file(zst_path)
        print("DBN file opened successfully")

        records = []
        total_processed = 0

        print("Starting to read records...")
        for i, record in enumerate(store):
            if i % 10000 == 0 and i > 0:
                print(f"📊 Processed {i} records...")

            try:
                record_dict = {
                    "ts_recv": record.ts_recv // 1000,
                    "ts_event": record.ts_event // 1000,
                    "rtype": record.rtype,
                    "publisher_id": record.publisher_id,
                    "instrument_id": record.instrument_id,
                    "action": record.action,
                    "side": record.side,
                    "depth": record.depth,
                    "price": record.price / 1000000000,
                    "size": record.size,
                    "flags": record.flags,
                    "ts_in_delta": record.ts_in_delta,
                    "sequence": record.sequence,
                }

                records.append(record_dict)
                total_processed += 1

                if len(records) >= batch_size:
                    insert_data(records)
                    records = []

            except Exception as e:
                print(f"❌ Error processing record {i}: {e}")
                break

        if records:
            print(f"📝 Inserting final batch of {len(records)} records")
            insert_data(records)

        print(f"✅ File processing completed: {total_processed} records")
        del store
        return total_processed

    except Exception as e:
        print(f"❌ Error processing file: {e}")
        import traceback

        traceback.print_exc()
        return 0


def process_all_trades_files(trades_folder, batch_size=50):
    """Process all .dbn.zst trade files in the specified folder"""
    pattern = os.path.join(trades_folder, "*.trades.dbn.zst")
    trade_files = glob.glob(pattern)

    if not trade_files:
        print(f"No trade files found in {trades_folder}")
        return

    trade_files.sort()
    print(f"Found {len(trade_files)} trade files to process")

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
            records_processed = process_single_trades_file(file_path, batch_size)
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


def list_trade_files(trades_folder):
    """List all available trade files"""
    pattern = os.path.join(trades_folder, "*.trades.dbn.zst")
    trade_files = glob.glob(pattern)

    if not trade_files:
        print(f"No trade files found in {trades_folder}")
        return

    trade_files.sort()
    print(f"Found {len(trade_files)} trade files:")
    for i, file_path in enumerate(trade_files, 1):
        size_mb = os.path.getsize(file_path) / (1024 * 1024)
        print(f"{i:3d}. {os.path.basename(file_path)} ({size_mb:.1f} MB)")


def test_trades_data():
    """Test function to verify trades data was inserted"""
    try:
        # Count total records
        response = requests.get(
            "http://questdb:9000/exec",
            params={"query": "SELECT COUNT(*) FROM trades_data"},
        )
        if response.status_code == 200:
            result = response.json()
            count = result["dataset"][0][0]
            print(f"📊 Total trades in database: {count:,}")

        # Get sample records
        response = requests.get(
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


def drop_table():
    """Drop the trades table"""
    try:
        response = requests.get(
            "http://questdb:9000/exec",
            params={"query": "DROP TABLE IF EXISTS trades_data"},
        )
        if response.status_code == 200:
            print("✅ Table dropped successfully")
        else:
            print(f"❌ Failed to drop table: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"❌ Error dropping table: {e}")


def main():
    parser = argparse.ArgumentParser(description="Trade Data Ingestion Tool")
    parser.add_argument(
        "--host", default="questdb", help="QuestDB host (default: questdb)"
    )
    parser.add_argument(
        "--port", type=int, default=9000, help="QuestDB port (default: 9000)"
    )
    parser.add_argument(
        "--folder",
        default="/data/trades",
        help="Trades folder path (default: /data/trades)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=50,
        help="Batch size for inserts (default: 50)",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Test connection
    subparsers.add_parser("test-connection", help="Test QuestDB connection")

    # Create table
    subparsers.add_parser("create-table", help="Create trades table")

    # Drop table
    subparsers.add_parser("drop-table", help="Drop trades table")

    # List files
    subparsers.add_parser("list-files", help="List available trade files")

    # Process single file
    process_single_parser = subparsers.add_parser(
        "process-file", help="Process a single trade file"
    )
    process_single_parser.add_argument("filename", help="Trade file to process")

    # Process all files
    subparsers.add_parser("process-all", help="Process all trade files in folder")

    # Test data
    subparsers.add_parser("test-data", help="Test inserted data")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Wait for QuestDB connection
    if not wait_for_questdb(args.host, args.port):
        print("QuestDB not available")
        sys.exit(1)

    # Execute commands
    if args.command == "test-connection":
        test_questdb_connection()

    elif args.command == "create-table":
        create_table_if_not_exists()

    elif args.command == "drop-table":
        drop_table()

    elif args.command == "list-files":
        list_trade_files(args.folder)

    elif args.command == "process-file":
        file_path = os.path.join(args.folder, args.filename)
        if not os.path.exists(file_path):
            print(f"File not found: {file_path}")
            sys.exit(1)

        if not create_table_if_not_exists():
            print("Failed to create table. Exiting.")
            sys.exit(1)

        records_processed = process_single_trades_file(file_path, args.batch_size)
        print(f"✅ Processing completed: {records_processed} records")

    elif args.command == "process-all":
        process_all_trades_files(args.folder, args.batch_size)

    elif args.command == "test-data":
        test_trades_data()


if __name__ == "__main__":
    main()
