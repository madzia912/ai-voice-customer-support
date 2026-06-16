"""Tests for the file-backed JobStore."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.jobs.store import JobNotFoundError, JobStore
from app.models import JobRecord, JobStatus


def _store(tmp_path: Path) -> JobStore:
    return JobStore(str(tmp_path / "jobs"))


def test_create_then_get_roundtrip(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.create(JobRecord(job_id="abc", prompt="hello"))

    fetched = store.get("abc")
    assert fetched.job_id == "abc"
    assert fetched.prompt == "hello"
    assert fetched.status is JobStatus.queued


def test_get_unknown_raises(tmp_path: Path) -> None:
    store = _store(tmp_path)
    with pytest.raises(JobNotFoundError):
        store.get("nope")


def test_try_get_returns_none_for_unknown(tmp_path: Path) -> None:
    store = _store(tmp_path)
    assert store.try_get("nope") is None


def test_update_mutates_only_provided_fields(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.create(JobRecord(job_id="abc", prompt="hi"))

    updated = store.update(
        "abc",
        status=JobStatus.completed,
        generated_text="response",
        audio_url="http://x/audio/abc.mp3",
        increment_attempts=True,
    )

    assert updated.status is JobStatus.completed
    assert updated.generated_text == "response"
    assert updated.audio_url == "http://x/audio/abc.mp3"
    assert updated.attempts == 1
    # Untouched fields remain.
    assert updated.prompt == "hi"


def test_writes_are_atomic_no_tmp_leftovers(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.create(JobRecord(job_id="abc", prompt="hi"))
    store.update("abc", status=JobStatus.processing)

    jobs_dir = tmp_path / "jobs"
    leftovers = [p for p in jobs_dir.iterdir() if p.name.endswith(".tmp")]
    assert leftovers == []


def test_path_traversal_in_job_id_is_neutralized(tmp_path: Path) -> None:
    store = _store(tmp_path)
    # Path-like ids should not escape the root.
    store.create(JobRecord(job_id="../evil", prompt="hi"))

    jobs_dir = tmp_path / "jobs"
    files = list(jobs_dir.iterdir())
    assert len(files) == 1
    assert files[0].parent == jobs_dir
