"""Shared retry policy for external API calls."""

from __future__ import annotations

import logging
from typing import Awaitable, Callable, TypeVar

import httpx
from tenacity import (
    AsyncRetrying,
    RetryError,
    before_sleep_log,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from .config import get_settings

T = TypeVar("T")

logger = logging.getLogger(__name__)


def is_retryable_status(exc: BaseException) -> bool:
    """Return True for transient errors that warrant another attempt."""
    if isinstance(exc, httpx.HTTPStatusError):
        # Retry on 408, 429, and any 5xx; explicit 4xx errors are caller bugs
        # and must fail fast.
        code = exc.response.status_code
        return code == 408 or code == 429 or 500 <= code < 600
    return isinstance(exc, (httpx.TimeoutException, httpx.TransportError))


async def call_with_retry(
    func: Callable[[], Awaitable[T]],
    *,
    operation: str,
) -> T:
    """Invoke ``func`` with exponential backoff retries.

    ``operation`` is used purely for logging context.
    """
    settings = get_settings()
    retryer = AsyncRetrying(
        stop=stop_after_attempt(settings.retry_max_attempts),
        wait=wait_exponential(
            multiplier=settings.retry_backoff_base_seconds, min=0.5, max=20.0
        ),
        # The predicate (not the exception *type*) decides what to retry, so a
        # 4xx HTTPStatusError fails fast even though its type is "retryable".
        retry=retry_if_exception(is_retryable_status),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    try:
        async for attempt in retryer:
            with attempt:
                try:
                    return await func()
                except httpx.HTTPStatusError as exc:
                    if is_retryable_status(exc):
                        logger.warning(
                            "retryable HTTP error",
                            extra={
                                "operation": operation,
                                "status_code": exc.response.status_code,
                            },
                        )
                    raise
    except RetryError as exc:  # pragma: no cover - defensive
        raise exc.last_attempt.exception()  # type: ignore[misc]
    raise RuntimeError("unreachable")  # pragma: no cover
