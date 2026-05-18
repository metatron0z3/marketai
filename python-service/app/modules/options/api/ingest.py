import os
import tempfile
import threading

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.core.job_manager import create_job, get_job, list_jobs
from app.modules.options.services.ingest import process_opra_file

router = APIRouter()


@router.post("/ingest/upload")
async def upload_opra_file(file: UploadFile = File(...)):
    if not file.filename.endswith((".dbn.zst", ".dbn")):
        raise HTTPException(status_code=400, detail="File must be a .dbn.zst or .dbn Databento file")

    contents = await file.read()
    suffix = ".dbn.zst" if file.filename.endswith(".dbn.zst") else ".dbn"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(contents)
    tmp.close()

    job_id = create_job(file.filename)
    threading.Thread(target=process_opra_file, args=(job_id, tmp.name), daemon=True).start()

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
