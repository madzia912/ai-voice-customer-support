"""Integration tests for the FastAPI surface using a fake RabbitMQ client."""

from __future__ import annotations

from typing import Iterator

import pytest
from fastapi.testclient import TestClient


class _FakeRabbitClient:
    def __init__(self) -> None:
        self.published: list = []

    async def connect(self):
        return None

    async def close(self) -> None:
        return None

    async def publish_job(self, message) -> None:
        self.published.append(message)


@pytest.fixture
def client(
    monkeypatch: pytest.MonkeyPatch, settings_env
) -> Iterator[tuple[TestClient, _FakeRabbitClient]]:
    fake = _FakeRabbitClient()

    # Replace the singleton accessor in both modules that import it.
    monkeypatch.setattr("app.api.main.get_rabbitmq_client", lambda: fake)
    monkeypatch.setattr("app.api.routes.generate.get_rabbitmq_client", lambda: fake)

    from app.api.main import create_app

    app = create_app()
    with TestClient(app) as c:
        yield c, fake


def test_health(client) -> None:
    c, _ = client
    resp = c.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_generate_enqueues_and_returns_job_id(client) -> None:
    c, fake = client

    resp = c.post("/generate", json={"prompt": "hi"})
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "queued"
    job_id = body["job_id"]
    assert job_id

    # A message hit the queue and a record was persisted.
    assert len(fake.published) == 1
    assert fake.published[0].job_id == job_id

    status = c.get(f"/status/{job_id}").json()
    assert status["status"] == "queued"


def test_generate_rejects_empty_prompt(client) -> None:
    c, _ = client
    resp = c.post("/generate", json={"prompt": ""})
    assert resp.status_code == 422


def test_status_404_for_unknown_job(client) -> None:
    c, _ = client
    assert c.get("/status/does-not-exist").status_code == 404


def test_result_returns_409_while_processing(client) -> None:
    c, _ = client
    job_id = c.post("/generate", json={"prompt": "hi"}).json()["job_id"]
    assert c.get(f"/result/{job_id}").status_code == 409


def test_result_returns_payload_when_completed(client) -> None:
    c, _ = client
    job_id = c.post("/generate", json={"prompt": "hi"}).json()["job_id"]

    from app.jobs import get_job_store
    from app.models import JobStatus

    get_job_store().update(
        job_id,
        status=JobStatus.completed,
        generated_text="hello there",
        audio_url="http://testserver/audio/abc.mp3",
    )

    body = c.get(f"/result/{job_id}").json()
    assert body == {
        "job_id": job_id,
        "status": "completed",
        "generated_text": "hello there",
        "audio_url": "http://testserver/audio/abc.mp3",
    }


def test_enqueue_failure_marks_job_failed_and_returns_503(
    monkeypatch: pytest.MonkeyPatch, client
) -> None:
    c, fake = client

    async def boom(_msg) -> None:
        raise RuntimeError("broker down")

    monkeypatch.setattr(fake, "publish_job", boom)

    resp = c.post("/generate", json={"prompt": "hi"})
    assert resp.status_code == 503

    # The created job should now be in `failed` state with an error attached.
    from app.jobs import get_job_store

    # The job_id is not returned on failure; scan the store directory.
    from pathlib import Path

    from app.config import get_settings

    jobs_dir = Path(get_settings().jobs_dir)
    files = list(jobs_dir.glob("*.json"))
    assert files, "expected a failed job record to exist"
    rec = get_job_store().get(files[0].stem)
    assert rec.status.value == "failed"
    assert "broker down" in (rec.error or "")
