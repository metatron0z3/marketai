import os
import tempfile
import threading
import uuid
from datetime import date

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field, model_validator

from app.core.job_manager import create_job, get_job, list_jobs
from app.modules.options.services.ingest import process_opra_file
from app.modules.options.services.massive_ingest import run_massive_ingest

router = APIRouter()

MAX_DATE_RANGE_DAYS = 365


class MassiveIngestRequest(BaseModel):
    underlying_symbol: str = Field(..., min_length=1, max_length=10)
    start_date: date
    end_date: date
    bar_timespan: str = Field("day", pattern="^(minute|hour|day|week|month)$")
    bar_multiplier: int = Field(1, ge=1, le=1440)
    include_expired: bool = True
    max_contracts: int = Field(100, ge=1, le=1000)

    @model_validator(mode="after")
    def validate_date_range(self) -> "MassiveIngestRequest":
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        if (self.end_date - self.start_date).days > MAX_DATE_RANGE_DAYS:
            raise ValueError(f"Date range must not exceed {MAX_DATE_RANGE_DAYS} days")
        return self


@router.post("/ingest/massive")
def ingest_from_massive(req: MassiveIngestRequest):
    """
    Discover option contracts for an underlying and ingest OHLCV aggregate bars
    from the Massive REST API.

    Requires MASSIVE_API_KEY to be set in the environment.
    Results are written to: options_contracts, options_bars, underlying_bars,
    and options_ingest_runs.

    Bars are NOT inserted into options_trades — that table is reserved for raw
    tick trades (Databento/OPRA path).
    """
    if not os.getenv("MASSIVE_API_KEY"):
        raise HTTPException(
            status_code=503,
            detail="MASSIVE_API_KEY is not configured on this server",
        )

    ingest_run_id = str(uuid.uuid4())
    job_id = create_job(
        f"massive:{req.underlying_symbol}:{req.start_date}:{req.end_date}",
        ingest_run_id=ingest_run_id,
        source="massive",
    )

    threading.Thread(
        target=run_massive_ingest,
        args=(
            req.underlying_symbol.upper(),
            req.start_date.isoformat(),
            req.end_date.isoformat(),
            req.bar_timespan,
            req.bar_multiplier,
            req.include_expired,
            req.max_contracts,
            ingest_run_id,
        ),
        daemon=True,
    ).start()

    return {
        "job_id": job_id,
        "ingest_run_id": ingest_run_id,
        "status": "pending",
        "message": f"Massive ingest queued for {req.underlying_symbol} "
                   f"{req.start_date} → {req.end_date}",
    }


# --- Legacy Databento/OPRA file upload (raw tick trades only) ---
# This endpoint accepts .dbn/.dbn.zst files from Databento and writes raw
# tick-level trades into options_trades. It is not part of the Massive ingest
# path and requires the 'databento' Python package to be installed.

@router.post("/ingest/upload", deprecated=True)
async def upload_opra_file(file: UploadFile = File(...)):
    """
    [LEGACY] Upload a Databento .dbn or .dbn.zst OPRA file for raw tick-trade ingestion.
    Use POST /ingest/massive for the Massive REST ingest path instead.
    """
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
