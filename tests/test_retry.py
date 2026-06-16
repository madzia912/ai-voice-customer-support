"""Behavioural tests for the shared retry policy."""

from __future__ import annotations

import httpx
import pytest

from app.retry import call_with_retry, is_retryable_status


def _http_error(status: int) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", "http://x")
    response = httpx.Response(status, request=request)
    return httpx.HTTPStatusError("boom", request=request, response=response)


def test_is_retryable_status_classifies_correctly() -> None:
    assert is_retryable_status(_http_error(429)) is True
    assert is_retryable_status(_http_error(500)) is True
    assert is_retryable_status(_http_error(503)) is True
    assert is_retryable_status(_http_error(408)) is True
    assert is_retryable_status(_http_error(400)) is False
    assert is_retryable_status(_http_error(404)) is False
    assert is_retryable_status(httpx.ConnectError("nope")) is True
    assert is_retryable_status(ValueError("nope")) is False


@pytest.mark.asyncio
async def test_retries_then_succeeds(settings_env, fast_retry) -> None:
    calls = {"n": 0}

    async def flaky() -> str:
        calls["n"] += 1
        if calls["n"] < 3:
            raise _http_error(503)
        return "ok"

    out = await call_with_retry(flaky, operation="test")
    assert out == "ok"
    assert calls["n"] == 3


@pytest.mark.asyncio
async def test_non_retryable_4xx_fails_immediately(settings_env, fast_retry) -> None:
    calls = {"n": 0}

    async def boom() -> str:
        calls["n"] += 1
        raise _http_error(400)

    with pytest.raises(httpx.HTTPStatusError):
        await call_with_retry(boom, operation="test")
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_exhausts_attempts_then_reraises(
    settings_env, fast_retry, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RETRY_MAX_ATTEMPTS", "2")
    from app.config import get_settings

    get_settings.cache_clear()

    calls = {"n": 0}

    async def always_503() -> str:
        calls["n"] += 1
        raise _http_error(503)

    with pytest.raises(httpx.HTTPStatusError):
        await call_with_retry(always_503, operation="test")
    assert calls["n"] == 2
