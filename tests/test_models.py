"""Sanity checks on the pydantic wire models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.models import GenerateRequest, JobMessage, JobRecord, JobStatus


def test_generate_request_requires_non_empty_prompt() -> None:
    with pytest.raises(ValidationError):
        GenerateRequest(prompt="")


def test_generate_request_enforces_max_length() -> None:
    with pytest.raises(ValidationError):
        GenerateRequest(prompt="x" * 4001)


def test_job_record_defaults() -> None:
    rec = JobRecord(job_id="abc", prompt="hi")
    assert rec.status is JobStatus.queued
    assert rec.attempts == 0
    assert rec.audio_url is None
    assert rec.created_at.tzinfo is not None  # always UTC-aware


def test_job_message_roundtrip() -> None:
    msg = JobMessage(job_id="abc", prompt="hi", voice_id=None)
    data = msg.model_dump_json()
    assert JobMessage.model_validate_json(data) == msg
