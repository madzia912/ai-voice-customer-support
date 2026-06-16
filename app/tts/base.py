"""TTS provider interface."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol


class TTSError(RuntimeError):
    """Raised when a TTS provider fails after retries."""


@dataclass(frozen=True)
class TTSResult:
    audio: bytes
    content_type: str  # e.g. "audio/mpeg"


class TTSService(Protocol):
    name: str

    async def synthesize(self, text: str, *, voice_id: Optional[str] = None) -> TTSResult:
        """Return synthesized audio for ``text``."""
        ...

    async def aclose(self) -> None:
        ...
