"""Shared fixtures.

The app uses a handful of ``lru_cache``\\d singletons (settings, job store,
audio storage) plus a module-level RabbitMQ client. We reset all of them
around each test so tests stay hermetic and ``DATA_DIR`` can point at a
per-test ``tmp_path``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

import pytest
from tenacity import wait_none


def _clear_caches() -> None:
    from app.config import get_settings
    from app.jobs.store import get_job_store
    from app.storage.local import get_audio_storage

    get_settings.cache_clear()
    get_job_store.cache_clear()
    get_audio_storage.cache_clear()

    import app.messaging.rabbitmq as rmq

    rmq._client = None


@pytest.fixture
def settings_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    """Point the app at a temp data dir with deterministic test settings.

    Critically, this also disables ``.env`` loading so a developer's local
    credentials never leak into the test process.
    """
    from app.config import Settings

    monkeypatch.setitem(
        Settings.model_config, "env_file", str(tmp_path / ".no_env_for_tests")
    )

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PUBLIC_BASE_URL", "http://testserver")
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")
    monkeypatch.setenv("RETRY_MAX_ATTEMPTS", "3")
    monkeypatch.setenv("RETRY_BACKOFF_BASE_SECONDS", "0.001")
    monkeypatch.setenv("LOG_LEVEL", "WARNING")
    # Default provider for tests that don't care which one is selected.
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    # Ensure the developer's local credentials don't leak into tests.
    for key in ("GROQ_API_KEY", "HF_API_KEY"):
        monkeypatch.delenv(key, raising=False)

    _clear_caches()

    # Regression guard: assert hermeticity *before* yielding to the test, while
    # the monkeypatch is still active. The assertions use ``not <value>`` so a
    # failure message never echoes the leaked secret into pytest output.
    from app.config import get_settings

    _s = get_settings()
    assert not _s.groq_api_key, "GROQ_API_KEY leaked into test settings"
    assert not _s.hf_api_key, "HF_API_KEY leaked into test settings"
    assert _s.elevenlabs_api_key == "test-key", (
        "ELEVENLABS_API_KEY not stubbed for tests"
    )

    yield
    _clear_caches()


@pytest.fixture
def fast_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    """Eliminate the exponential backoff so retry tests run instantly."""
    monkeypatch.setattr("app.retry.wait_exponential", lambda **_: wait_none())
