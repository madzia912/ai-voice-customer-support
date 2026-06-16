"""Pydantic models shared between the API, queue, and worker."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    queued = "queued"
    processing = "processing"
    completed = "completed"
    failed = "failed"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class GenerateRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=4000)
    voice_id: Optional[str] = Field(
        default=None,
        description="ElevenLabs voice id override; falls back to server default.",
    )


class GenerateResponse(BaseModel):
    job_id: str
    status: JobStatus


class JobRecord(BaseModel):
    """Canonical record persisted by the JobStore."""

    job_id: str
    status: JobStatus = JobStatus.queued
    prompt: str
    voice_id: Optional[str] = None

    generated_text: Optional[str] = None
    audio_path: Optional[str] = None
    audio_url: Optional[str] = None
    error: Optional[str] = None

    attempts: int = 0
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class JobMessage(BaseModel):
    """Envelope placed on the RabbitMQ work queue."""

    job_id: str
    prompt: str
    voice_id: Optional[str] = None


class StatusResponse(BaseModel):
    job_id: str
    status: JobStatus
    error: Optional[str] = None
    updated_at: datetime


class ResultResponse(BaseModel):
    job_id: str
    status: JobStatus
    generated_text: Optional[str] = None
    audio_url: Optional[str] = None
