"""LLM provider interface."""

from __future__ import annotations

from typing import Protocol


class LLMError(RuntimeError):
    """Raised when an LLM provider fails after retries."""


class LLMService(Protocol):
    name: str

    async def generate(self, prompt: str, *, system_prompt: str) -> str:
        """Return the assistant response for ``prompt``."""
        ...

    async def aclose(self) -> None:
        ...
