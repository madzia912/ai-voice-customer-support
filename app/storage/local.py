"""Local filesystem implementation of :class:`AudioStorage`."""

from __future__ import annotations

import os
import tempfile
from functools import lru_cache
from pathlib import Path

from ..config import get_settings
from .base import StoredAudio

_EXT_BY_CONTENT_TYPE = {
    "audio/mpeg": ".mp3",
    "audio/mp3": ".mp3",
    "audio/wav": ".wav",
    "audio/ogg": ".ogg",
}


class LocalAudioStorage:
    def __init__(self, root: str, public_base_url: str, url_prefix: str = "/audio") -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)
        self._public_base_url = public_base_url.rstrip("/")
        self._url_prefix = "/" + url_prefix.strip("/")

    def save(
        self,
        job_id: str,
        data: bytes,
        *,
        content_type: str = "audio/mpeg",
    ) -> StoredAudio:
        ext = _EXT_BY_CONTENT_TYPE.get(content_type, ".bin")
        safe = job_id.replace("/", "_").replace("..", "_")
        filename = f"{safe}{ext}"
        final_path = self._root / filename

        fd, tmp_path = tempfile.mkstemp(prefix=f".{safe}.", suffix=ext, dir=str(self._root))
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
            os.replace(tmp_path, final_path)
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

        url = f"{self._public_base_url}{self._url_prefix}/{filename}"
        return StoredAudio(path=str(final_path), url=url)


@lru_cache(maxsize=1)
def get_audio_storage() -> LocalAudioStorage:
    s = get_settings()
    return LocalAudioStorage(root=s.audio_dir, public_base_url=s.public_base_url)
