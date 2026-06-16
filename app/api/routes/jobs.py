"""GET /status/{job_id} and GET /result/{job_id}."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from ...jobs import get_job_store
from ...jobs.store import JobNotFoundError
from ...models import JobStatus, ResultResponse, StatusResponse

router = APIRouter(tags=["jobs"])


@router.get("/status/{job_id}", response_model=StatusResponse)
async def get_status(job_id: str) -> StatusResponse:
    try:
        record = get_job_store().get(job_id)
    except JobNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="job not found")
    return StatusResponse(
        job_id=record.job_id,
        status=record.status,
        error=record.error,
        updated_at=record.updated_at,
    )


@router.get("/result/{job_id}", response_model=ResultResponse)
async def get_result(job_id: str) -> ResultResponse:
    try:
        record = get_job_store().get(job_id)
    except JobNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="job not found")

    if record.status == JobStatus.failed:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"job_id": job_id, "status": record.status, "error": record.error},
        )
    if record.status != JobStatus.completed:
        # Result is not ready yet — 409 is the conventional "wrong state" code.
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={"job_id": job_id, "status": record.status},
        )

    return ResultResponse(
        job_id=record.job_id,
        status=record.status,
        generated_text=record.generated_text,
        audio_url=record.audio_url,
    )
