import os
import tempfile
import threading

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.modules.options.services.ingest import (
    _new_job,
    get_job,
    list_jobs,
    process_opra_file,
)

router = APIRouter()


@router.post("/ingest/upload")
async def upload_opra_file(file: UploadFile = File(...)):
    if not file.filename.endswith((".dbn.zst", ".dbn")):
        raise HTTPException(status_code=400, detail="File must be a .dbn.zst or .dbn Databento file")

    contents = await file.read()
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[1])
    tmp.write(contents)
    tmp.close()

    job_id = _new_job(file.filename)
    thread = threading.Thread(target=process_opra_file, args=(job_id, tmp.name), daemon=True)
    thread.start()

    return {"job_id": job_id, "status": "pending", "message": "OPRA file queued for processing"}


@router.get("/ingest/jobs")
def get_all_jobs():
    return list_jobs()


@router.get("/ingest/jobs/{job_id}")
def get_job_status(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job
