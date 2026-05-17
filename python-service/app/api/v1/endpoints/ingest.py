import logging
import os
import uuid
import tempfile
import zipfile
import shutil
import threading
from fastapi import APIRouter, HTTPException, UploadFile, File, Form, BackgroundTasks
from typing import List, Dict, Optional
from datetime import datetime
import databento as db
import requests
import psycopg2

logger = logging.getLogger(__name__)

router = APIRouter()

# In-memory job storage (in production, use a database)
ingestion_jobs: Dict[str, Dict] = {}
ingestion_lock = threading.Lock()


def execute_query(query: str):
    """Execute a query using QuestDB's HTTP interface"""
    try:
        response = requests.get("http://questdb:9000/exec", params={"query": query})
        response.raise_for_status()
        result = response.json()

        if "error" in result:
            logger.error(f"Query error: {result['error']}")
            return None

        return result
    except requests.exceptions.RequestException as e:
        logger.error(f"Error executing query: {e}")
        return None


def create_trades_table():
    """Create the trades_data table if it doesn't exist"""
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
            logger.info("Trades table created/verified successfully")
            return True
        else:
            logger.error(f"Failed to create table: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        logger.error(f"Error creating table: {e}")
        return False


def get_questdb_connection():
    """Get a connection to QuestDB via PostgreSQL wire protocol"""
    return psycopg2.connect(
        host="questdb",
        port=8812,
        user="admin",
        password="quest",
        database="qdb"
    )


def insert_batch(records: List[Dict]) -> bool:
    """Insert a batch of records into QuestDB using PostgreSQL wire protocol"""
    if not records:
        return True

    conn = None
    cursor = None
    try:
        conn = get_questdb_connection()
        cursor = conn.cursor()

        # Build INSERT query with placeholders
        insert_query = """
        INSERT INTO trades_data
        (ts_recv, ts_event, rtype, publisher_id, instrument_id, action, side, depth, price, size, flags, ts_in_delta, sequence)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """

        # Prepare data tuples
        data_tuples = [
            (
                record['ts_recv'],
                record['ts_event'],
                record['rtype'],
                record['publisher_id'],
                record['instrument_id'],
                record['action'],
                record['side'],
                record['depth'],
                record['price'],
                record['size'],
                record['flags'],
                record['ts_in_delta'],
                record['sequence']
            )
            for record in records
        ]

        # Execute batch insert
        cursor.executemany(insert_query, data_tuples)
        conn.commit()

        return True

    except Exception as e:
        logger.error(f"Insert error: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def update_job_status(job_id: str, updates: Dict):
    """Thread-safe job status update"""
    with ingestion_lock:
        if job_id in ingestion_jobs:
            ingestion_jobs[job_id].update(updates)


def process_dbn_file(file_path: str, job_id: str, file_index: int = 0, total_files: int = 1, batch_size: int = 1000) -> int:
    """Process a .dbn.zst file and insert into QuestDB"""
    try:
        store = db.DBNStore.from_file(file_path)
        logger.info(f"Job {job_id}: Processing file {file_index + 1}/{total_files}: {os.path.basename(file_path)}")

        records = []
        total_processed = 0

        for i, record in enumerate(store):
            if i % 5000 == 0 and i > 0:
                # Update job progress
                base_progress = (file_index / total_files) * 100
                file_progress = 0  # We don't know total records in advance
                overall_progress = min(95, base_progress + (file_progress / total_files))

                update_job_status(job_id, {
                    'recordsProcessed': total_processed,
                    'progress': int(overall_progress),
                    'currentFile': f"{file_index + 1}/{total_files}"
                })
                logger.info(f"Job {job_id}: {total_processed} records processed from file {file_index + 1}/{total_files}")

            try:
                record_dict = {
                    "ts_recv": record.ts_recv // 1000,
                    "ts_event": record.ts_event // 1000,
                    "rtype": int(record.rtype),
                    "publisher_id": record.publisher_id,
                    "instrument_id": record.instrument_id,
                    "action": str(record.action) if hasattr(record.action, 'name') else str(record.action),
                    "side": str(record.side) if hasattr(record.side, 'name') else str(record.side),
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
                    if not insert_batch(records):
                        raise Exception("Failed to insert batch")
                    records = []

            except Exception as e:
                logger.error(f"Error processing record {i}: {e}")
                break

        # Insert remaining records
        if records:
            if not insert_batch(records):
                raise Exception("Failed to insert final batch")

        logger.info(f"Job {job_id}: File {file_index + 1}/{total_files} completed: {total_processed} records")
        del store
        return total_processed

    except Exception as e:
        logger.error(f"Job {job_id}: Error processing file {file_path}: {e}")
        raise


def process_ingestion_background(job_id: str, file_path: str, table: str, is_zip: bool):
    """Background processing function"""
    temp_dir = None
    try:
        logger.info(f"Job {job_id}: Starting background processing")

        # Create table if needed
        if not create_trades_table():
            raise Exception("Failed to create table")

        total_records = 0

        if is_zip:
            # Extract ZIP file
            logger.info(f"Job {job_id}: Extracting ZIP file...")
            update_job_status(job_id, {'status': 'processing', 'progress': 5})

            temp_dir = tempfile.mkdtemp()
            extract_dir = os.path.join(temp_dir, 'extracted')
            os.makedirs(extract_dir, exist_ok=True)

            with zipfile.ZipFile(file_path, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)

            # Find all .dbn.zst files recursively
            dbn_files = []
            for root, dirs, files in os.walk(extract_dir):
                for fname in files:
                    if fname.endswith('.dbn.zst'):
                        dbn_files.append(os.path.join(root, fname))

            logger.info(f"Job {job_id}: Found {len(dbn_files)} .dbn.zst files in ZIP")
            update_job_status(job_id, {
                'totalFiles': len(dbn_files),
                'progress': 10
            })

            # Process each file
            for idx, dbn_file in enumerate(dbn_files):
                records = process_dbn_file(dbn_file, job_id, idx, len(dbn_files))
                total_records += records

                file_progress = int(((idx + 1) / len(dbn_files)) * 90) + 10
                update_job_status(job_id, {
                    'recordsProcessed': total_records,
                    'progress': file_progress
                })

        else:
            # Process single .dbn.zst file
            update_job_status(job_id, {'status': 'processing', 'progress': 10, 'totalFiles': 1})
            total_records = process_dbn_file(file_path, job_id, 0, 1)

        # Job completed
        update_job_status(job_id, {
            'status': 'completed',
            'progress': 100,
            'recordsProcessed': total_records,
            'totalRecords': total_records,
            'endTime': datetime.utcnow().isoformat()
        })

        logger.info(f"Job {job_id}: Completed successfully - {total_records} records ingested")

    except Exception as e:
        logger.exception(f"Job {job_id}: Processing failed")
        update_job_status(job_id, {
            'status': 'failed',
            'error': str(e),
            'endTime': datetime.utcnow().isoformat()
        })

    finally:
        # Cleanup
        try:
            if is_zip and temp_dir and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
            if os.path.exists(file_path):
                os.remove(file_path)
        except Exception as e:
            logger.error(f"Job {job_id}: Cleanup error: {e}")


@router.post("/upload")
async def upload_and_ingest(
    file: UploadFile = File(...),
    table: str = Form(...)
):
    """Upload and ingest a data file - returns immediately and processes in background"""
    job_id = str(uuid.uuid4())

    logger.info(f"Received upload: {file.filename} for table {table}")

    # Validate table name
    if table != "trades_data":
        raise HTTPException(status_code=400, detail=f"Invalid table: {table}")

    # Validate file extension
    is_zip = file.filename.endswith('.zip')
    is_dbn = file.filename.endswith('.dbn.zst')

    if not (is_dbn or is_zip):
        raise HTTPException(status_code=400, detail="File must be .dbn.zst or .zip")

    # Create job
    with ingestion_lock:
        ingestion_jobs[job_id] = {
            "id": job_id,
            "filename": file.filename,
            "table": table,
            "status": "uploading",
            "progress": 0,
            "recordsProcessed": 0,
            "totalRecords": 0,
            "totalFiles": 0,
            "currentFile": "",
            "startTime": datetime.utcnow().isoformat()
        }

    try:
        # Save uploaded file to temp location
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[1])
        temp_path = temp_file.name

        logger.info(f"Job {job_id}: Saving uploaded file to {temp_path}")

        # Save file
        contents = await file.read()
        with open(temp_path, 'wb') as f:
            f.write(contents)

        logger.info(f"Job {job_id}: File saved ({len(contents)} bytes), starting background processing")

        # Start background processing in a thread
        processing_thread = threading.Thread(
            target=process_ingestion_background,
            args=(job_id, temp_path, table, is_zip),
            daemon=True
        )
        processing_thread.start()

        # Return immediately
        return {
            "jobId": job_id,
            "message": "Upload successful, processing started in background",
            "status": "processing"
        }

    except Exception as e:
        logger.exception(f"Upload failed for job {job_id}")
        update_job_status(job_id, {
            "status": "failed",
            "error": str(e),
            "endTime": datetime.utcnow().isoformat()
        })

        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@router.get("/jobs")
async def get_ingestion_jobs():
    """Get all ingestion jobs"""
    with ingestion_lock:
        return list(ingestion_jobs.values())


@router.get("/jobs/{job_id}")
async def get_ingestion_job(job_id: str):
    """Get a specific ingestion job status"""
    with ingestion_lock:
        if job_id not in ingestion_jobs:
            raise HTTPException(status_code=404, detail="Job not found")
        return ingestion_jobs[job_id]
