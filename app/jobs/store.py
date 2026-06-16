"""File-backed job store.

The store is intentionally simple: one JSON file per job under
``${DATA_DIR}/jobs/<job_id>.json``. Writes are atomic via ``os.replace`` so
concurrent readers never observe a half-written record. The same on-disk
contract is shared by the API process and the worker process, which is the
minimum required for a multi-process MVP without standing up Redis/Postgres.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Optional

from ..config import get_settings
from ..models import JobRecord, JobStatus


class JobNotFoundError(KeyError):
    """Raised when a requested job id does not exist."""


class JobStore:
    def __init__(self, root: str) -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _safe_id(job_id: str) -> str:
        # Guard against path traversal on the public job id.
        return job_id.replace("/", "_").replace("\\", "_").replace("..", "_")

    def _path(self, job_id: str) -> Path:
        return self._root / f"{self._safe_id(job_id)}.json"

    def create(self, record: JobRecord) -> JobRecord:
        self._write(record)
        return record

    def get(self, job_id: str) -> JobRecord:
        path = self._path(job_id)
        if not path.exists():
            raise JobNotFoundError(job_id)
        with path.open("r", encoding="utf-8") as fh:
            return JobRecord.model_validate_json(fh.read())

    def try_get(self, job_id: str) -> Optional[JobRecord]:
        try:
            return self.get(job_id)
        except JobNotFoundError:
            return None

    def update(
        self,
        job_id: str,
        *,
        status: Optional[JobStatus] = None,
        generated_text: Optional[str] = None,
        audio_path: Optional[str] = None,
        audio_url: Optional[str] = None,
        error: Optional[str] = None,
        increment_attempts: bool = False,
    ) -> JobRecord:
        record = self.get(job_id)
        if status is not None:
            record.status = status
        if generated_text is not None:
            record.generated_text = generated_text
        if audio_path is not None:
            record.audio_path = audio_path
        if audio_url is not None:
            record.audio_url = audio_url
        if error is not None:
            record.error = error
        if increment_attempts:
            record.attempts += 1
        record.updated_at = datetime.now(timezone.utc)
        self._write(record)
        return record

    def _write(self, record: JobRecord) -> None:
        safe = self._safe_id(record.job_id)
        path = self._root / f"{safe}.json"
        payload = record.model_dump_json()
        # Atomic write: tmp file in the same directory + os.replace.
        fd, tmp_path = tempfile.mkstemp(
            prefix=f".{safe}.", suffix=".tmp", dir=str(self._root)
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(payload)
            os.replace(tmp_path, path)
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise


@lru_cache(maxsize=1)
def get_job_store() -> JobStore:
    return JobStore(get_settings().jobs_dir)
