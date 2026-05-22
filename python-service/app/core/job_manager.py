import threading
import uuid
from datetime import datetime, timezone


_jobs: dict[str, dict] = {}
_lock = threading.Lock()


def create_job(filename: str, **extra) -> str:
    job_id = str(uuid.uuid4())
    with _lock:
        _jobs[job_id] = {
            "id": job_id,
            "filename": filename,
            "status": "pending",
            "records_processed": 0,
            "error": None,
            "start_time": datetime.now(timezone.utc).isoformat(),
            "end_time": None,
            **extra,
        }
    return job_id


def update_job(job_id: str, **kwargs) -> None:
    with _lock:
        if job_id in _jobs:
            _jobs[job_id].update(kwargs)


def get_job(job_id: str) -> dict | None:
    return _jobs.get(job_id)


def list_jobs() -> list[dict]:
    return list(_jobs.values())
