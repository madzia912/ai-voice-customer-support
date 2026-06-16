"""Storage abstraction for generated audio artifacts.

This is intentionally thin so it can be swapped for an S3-compatible backend
(e.g. MinIO, AWS S3) without touching the worker pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class StoredAudio:
    path: str  # absolute on-disk path (or backend-specific key)
    url: str   # publicly resolvable URL


class AudioStorage(Protocol):
    def save(self, job_id: str, data: bytes, *, content_type: str = "audio/mpeg") -> StoredAudio:
        """Persist audio bytes for ``job_id`` and return its locator."""
        ...
