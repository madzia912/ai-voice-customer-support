"""Tests for the per-message worker pipeline."""

from __future__ import annotations

from typing import Optional

import pytest

from app.jobs import get_job_store
from app.models import JobMessage, JobRecord, JobStatus
from app.tts.base import TTSResult
from app.worker.handler import JobHandler


class _FakeLLM:
    name = "fake-llm"

    def __init__(self, response: str = "generated reply") -> None:
        self._response = response
        self.calls: list[str] = []

    async def generate(self, prompt: str, *, system_prompt: str) -> str:
        self.calls.append(prompt)
        return self._response

    async def aclose(self) -> None:
        pass


class _FakeTTS:
    name = "fake-tts"

    def __init__(self, audio: bytes = b"AUDIO") -> None:
        self._audio = audio
        self.calls: list[tuple[str, Optional[str]]] = []

    async def synthesize(self, text: str, *, voice_id: Optional[str] = None) -> TTSResult:
        self.calls.append((text, voice_id))
        return TTSResult(audio=self._audio, content_type="audio/mpeg")

    async def aclose(self) -> None:
        pass


class _BoomLLM(_FakeLLM):
    async def generate(self, prompt: str, *, system_prompt: str) -> str:  # type: ignore[override]
        raise RuntimeError("llm down")


@pytest.fixture
def seeded_job(settings_env) -> JobRecord:
    rec = JobRecord(job_id="job-1", prompt="hello", voice_id=None)
    get_job_store().create(rec)
    return rec


@pytest.mark.asyncio
async def test_happy_path_completes_job_and_writes_audio(seeded_job) -> None:
    llm, tts = _FakeLLM("hi back"), _FakeTTS(b"BYTES")
    handler = JobHandler(llm=llm, tts=tts)

    await handler.handle(JobMessage(job_id="job-1", prompt="hello"))

    record = get_job_store().get("job-1")
    assert record.status is JobStatus.completed
    assert record.generated_text == "hi back"
    assert record.audio_url and record.audio_url.endswith("/audio/job-1.mp3")
    assert record.attempts == 1

    from pathlib import Path

    assert Path(record.audio_path or "").read_bytes() == b"BYTES"
    assert llm.calls == ["hello"]
    assert tts.calls == [("hi back", None)]


@pytest.mark.asyncio
async def test_failure_marks_job_failed_and_reraises(seeded_job) -> None:
    handler = JobHandler(llm=_BoomLLM(), tts=_FakeTTS())

    with pytest.raises(RuntimeError, match="llm down"):
        await handler.handle(JobMessage(job_id="job-1", prompt="hello"))

    record = get_job_store().get("job-1")
    assert record.status is JobStatus.failed
    assert "llm down" in (record.error or "")
    assert record.attempts == 1


@pytest.mark.asyncio
async def test_idempotent_skips_already_completed_job(seeded_job) -> None:
    store = get_job_store()
    store.update(
        "job-1",
        status=JobStatus.completed,
        generated_text="prior",
        audio_url="http://testserver/audio/job-1.mp3",
    )

    llm, tts = _FakeLLM(), _FakeTTS()
    handler = JobHandler(llm=llm, tts=tts)

    await handler.handle(JobMessage(job_id="job-1", prompt="hello"))

    # Neither external service was called; record is unchanged.
    assert llm.calls == []
    assert tts.calls == []
    assert store.get("job-1").generated_text == "prior"


@pytest.mark.asyncio
async def test_unknown_job_message_is_dropped_silently(settings_env) -> None:
    handler = JobHandler(llm=_FakeLLM(), tts=_FakeTTS())
    # Should not raise — the consumer will ack and move on.
    await handler.handle(JobMessage(job_id="ghost", prompt="hello"))
