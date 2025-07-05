import databento as db
import pandas as pd
import psycopg2
from config import Config
import time
import zipfile
import os
import tempfile
import zstd
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


def test_questdb_connection():
    """Test QuestDB connection."""
    logging.info("Testing QuestDB connection...")
    try:
        conn = psycopg2.connect(
            host=Config.QUESTDB_HOST,
            port=Config.QUESTDB_PORT,
            user=Config.QUESTDB_USER,
            password=Config.QUESTDB_PASSWORD,
            dbname=Config.QUESTDB_DATABASE,
        )
        conn.close()
        logging.info("QuestDB connection test successful.")
        return True
    except Exception as e:
        logging.error(f"QuestDB connection test failed: {e}")
        return False


def create_tbbo_table(conn):
    """Create the tbbo_data table in QuestDB."""
    logging.info("Creating tbbo_data table...")
    with conn.cursor() as cursor:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tbbo_data (
                ts_recv TIMESTAMP,
                ts_event TIMESTAMP,
                rtype SYMBOL,
                publisher_id INT,
                instrument_id INT,
                action SYMBOL,
                side SYMBOL,
                depth INT,
                price DOUBLE,
                size LONG,
                flags INT,
                ts_in_delta LONG,
                sequence LONG,
                bid_px_00 DOUBLE,
                ask_px_00 DOUBLE,
                bid_sz_00 LONG,
                ask_sz_00 LONG,
                bid_ct_00 LONG,
                ask_ct_00 LONG,
                symbol SYMBOL
            ) TIMESTAMP(ts_event) PARTITION BY DAY;
        """)
        conn.commit()
    logging.info("Table tbbo_data created or already exists.")


def insert_tbbo_data(conn, df):
    """Insert TBBO data into QuestDB."""
    logging.info(f"Inserting {len(df)} records into tbbo_data...")
    with conn.cursor() as cursor:
        for _, row in df.iterrows():
            cursor.execute(
                """
                INSERT INTO tbbo_data (
                    ts_recv, ts_event, rtype, publisher_id, instrument_id,
                    action, side, depth, price, size, flags, ts_in_delta,
                    sequence, bid_px_00, ask_px_00, bid_sz_00, ask_sz_00,
                    bid_ct_00, ask_ct_00, symbol
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
            """,
                (
                    pd.Timestamp(row["ts_recv"]).to_pydatetime()
                    if pd.notnull(row["ts_recv"])
                    else None,
                    pd.Timestamp(row["ts_event"]).to_pydatetime()
                    if pd.notnull(row["ts_event"])
                    else None,
                    row["rtype"] if pd.notnull(row["rtype"]) else None,
                    row["publisher_id"] if pd.notnull(row["publisher_id"]) else None,
                    row["instrument_id"] if pd.notnull(row["instrument_id"]) else None,
                    row["action"] if pd.notnull(row["action"]) else None,
                    row["side"] if pd.notnull(row["side"]) else None,
                    row["depth"] if pd.notnull(row["depth"]) else None,
                    row["price"] if pd.notnull(row["price"]) else None,
                    row["size"] if pd.notnull(row["size"]) else None,
                    row["flags"] if pd.notnull(row["flags"]) else None,
                    row["ts_in_delta"] if pd.notnull(row["ts_in_delta"]) else None,
                    row["sequence"] if pd.notnull(row["sequence"]) else None,
                    row["bid_px_00"] if pd.notnull(row["bid_px_00"]) else None,
                    row["ask_px_00"] if pd.notnull(row["ask_px_00"]) else None,
                    row["bid_sz_00"] if pd.notnull(row["bid_sz_00"]) else None,
                    row["ask_sz_00"] if pd.notnull(row["ask_sz_00"]) else None,
                    row["bid_ct_00"] if pd.notnull(row["bid_ct_00"]) else None,
                    row["ask_ct_00"] if pd.notnull(row["ask_ct_00"]) else None,
                    row["symbol"] if pd.notnull(row["symbol"]) else None,
                ),
            )
        conn.commit()
    logging.info(f"Inserted {len(df)} records.")


def decompress_zst(zst_path, output_path):
    """Decompress a .zst file to .dbn using streaming."""
    logging.info(f"Decompressing {zst_path} to {output_path}...")
    try:
        with open(zst_path, "rb") as zst_file, open(output_path, "wb") as dbn_file:
            decompressor = zstd.ZstdDecompressor()
            decompressor.copy_stream(zst_file, dbn_file)
        logging.info(f"Decompressed {zst_path} successfully.")
    except Exception as e:
        logging.error(f"Failed to decompress {zst_path}: {e}")
        raise


def process_tbbo_file(file_path):
    """Read and process the compressed DBF file."""
    logging.info(f"Processing ZIP file: {file_path}")
    if not test_questdb_connection():
        raise Exception("Cannot proceed without QuestDB connection.")

    conn = psycopg2.connect(
        host=Config.QUESTDB_HOST,
        port=Config.QUESTDB_PORT,
        user=Config.QUESTDB_USER,
        password=Config.QUESTDB_PASSWORD,
        dbname=Config.QUESTDB_DATABASE,
    )
    try:
        create_tbbo_table(conn)

        # Extract ZIP file
        logging.info("Extracting ZIP file...")
        with tempfile.TemporaryDirectory() as tmpdirname:
            with zipfile.ZipFile(file_path, "r") as zip_ref:
                zip_ref.extractall(tmpdirname)
                logging.info(f"Extracted ZIP to {tmpdirname}")
                # Process one .dbn.zst file for testing
                zst_files = [
                    f for f in os.listdir(tmpdirname) if f.endswith(".dbn.zst")
                ][:1]
                logging.info(f"Found {len(zst_files)} .dbn.zst files: {zst_files}")
                for zst_file in zst_files:
                    zst_path = os.path.join(tmpdirname, zst_file)
                    dbn_path = os.path.join(tmpdirname, zst_file.replace(".zst", ""))
                    decompress_zst(zst_path, dbn_path)

                    # Read DBN file using databento
                    logging.info(f"Reading DBN file: {dbn_path}")
                    try:
                        dbf = db.DBNStore.from_file(dbn_path)
                        chunk_size = 500  # Further reduced
                        for chunk in dbf.to_df(
                            chunks=chunk_size, symbols=["SPY", "QQQ", "TSLA"]
                        ):
                            insert_tbbo_data(conn, chunk)
                        os.remove(dbn_path)
                        logging.info(f"Processed and removed {dbn_path}")
                    except Exception as e:
                        logging.error(f"Failed to process {zst_file}: {e}")
                        continue
    finally:
        conn.close()
        logging.info("Closed QuestDB connection.")


def main():
    """Main function to ingest TBBO data."""
    logging.info("Starting TBBO data ingestion...")
    file_path = (
        "data/tbbo/XNAS-20250630-3K464RPTEN.zip"
        if os.path.exists("data/tbbo/XNAS-20250630-3K464RPTEN.zip")
        else "/src/data/tbbo/XNAS-20250630-3K464RPTEN.zip"
    )
    if not os.path.exists(file_path):
        logging.error(f"ZIP file not found at {file_path}")
        raise FileNotFoundError(f"ZIP file not found at {file_path}")
    process_tbbo_file(file_path)
    logging.info("TBBO data ingestion completed.")


if __name__ == "__main__":
    main()
