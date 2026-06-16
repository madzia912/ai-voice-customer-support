"""Per-message processing pipeline: LLM -> TTS -> storage -> status update."""

from __future__ import annotations

import logging

from ..config import get_settings
from ..jobs import get_job_store
from ..jobs.store import JobNotFoundError
from ..llm import LLMService
from ..logging_config import bind
from ..models import JobMessage, JobStatus
from ..storage import get_audio_storage
from ..tts import TTSService

_logger = logging.getLogger(__name__)


class JobHandler:
    """Stateful per-worker handler that owns the LLM + TTS HTTP clients."""

    def __init__(self, llm: LLMService, tts: TTSService) -> None:
        self._llm = llm
        self._tts = tts
        self._store = get_job_store()
        self._storage = get_audio_storage()
        self._settings = get_settings()

    async def handle(self, msg: JobMessage) -> None:
        log = bind(_logger, job_id=msg.job_id)

        try:
            record = self._store.get(msg.job_id)
        except JobNotFoundError:
            # Message references a job we no longer know about; ack and move on.
            log.warning("dropping message for unknown job")
            return

        # Idempotency: skip work that's already done.
        if record.status == JobStatus.completed and record.audio_url:
            log.info("job already completed; skipping")
            return

        self._store.update(
            msg.job_id, status=JobStatus.processing, increment_attempts=True
        )

        try:
            log.info("calling LLM", extra={"provider": self._llm.name})
            text = await self._llm.generate(
                msg.prompt, system_prompt=self._settings.llm_system_prompt
            )
            self._store.update(msg.job_id, generated_text=text)

            log.info("calling TTS", extra={"provider": self._tts.name})
            tts_result = await self._tts.synthesize(text, voice_id=msg.voice_id)

            stored = self._storage.save(
                msg.job_id, tts_result.audio, content_type=tts_result.content_type
            )
            self._store.update(
                msg.job_id,
                status=JobStatus.completed,
                audio_path=stored.path,
                audio_url=stored.url,
            )
            log.info("job completed", extra={"audio_url": stored.url})
        except Exception as exc:
            # Retries on transient errors happen inside the provider; reaching
            # here means we've exhausted them or hit a non-retryable error.
            self._store.update(
                msg.job_id, status=JobStatus.failed, error=str(exc)
            )
            log.exception("job failed")
            raise
