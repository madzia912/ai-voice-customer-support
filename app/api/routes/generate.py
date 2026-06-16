"""POST /generate — enqueue a voice generation job."""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, HTTPException, status

from ...jobs import get_job_store
from ...logging_config import bind
from ...messaging import get_rabbitmq_client
from ...models import GenerateRequest, GenerateResponse, JobMessage, JobRecord, JobStatus

router = APIRouter(tags=["jobs"])
_logger = logging.getLogger(__name__)


@router.post(
    "/generate",
    response_model=GenerateResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def generate(req: GenerateRequest) -> GenerateResponse:
    job_id = uuid.uuid4().hex
    log = bind(_logger, job_id=job_id)

    store = get_job_store()
    record = JobRecord(
        job_id=job_id,
        prompt=req.prompt,
        voice_id=req.voice_id,
        status=JobStatus.queued,
    )
    store.create(record)
    log.info("job created")

    try:
        await get_rabbitmq_client().publish_job(
            JobMessage(job_id=job_id, prompt=req.prompt, voice_id=req.voice_id)
        )
    except Exception as exc:
        # Roll the job into a failed state so clients see a clear error
        # instead of a job that is forever "queued".
        store.update(job_id, status=JobStatus.failed, error=f"enqueue_failed: {exc!s}")
        log.exception("failed to enqueue job")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Failed to enqueue job",
        ) from exc

    return GenerateResponse(job_id=job_id, status=JobStatus.queued)
