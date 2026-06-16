"""ElevenLabs Text-to-Speech provider."""

from __future__ import annotations

from typing import Optional

import httpx

from ..config import Settings, get_settings
from ..retry import call_with_retry
from .base import TTSError, TTSResult


class ElevenLabsTTSService:
    name = "elevenlabs"

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        default_voice_id: str,
        model_id: str,
        timeout: float,
    ) -> None:
        if not api_key:
            raise TTSError("ELEVENLABS_API_KEY is required")
        self._default_voice_id = default_voice_id
        self._model_id = model_id
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=httpx.Timeout(timeout, connect=10.0),
            headers={
                "xi-api-key": api_key,
                "Accept": "audio/mpeg",
                "Content-Type": "application/json",
            },
        )

    async def synthesize(self, text: str, *, voice_id: Optional[str] = None) -> TTSResult:
        vid = voice_id or self._default_voice_id
        payload = {
            "text": text,
            "model_id": self._model_id,
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
        }

        async def _do() -> TTSResult:
            resp = await self._client.post(f"/v1/text-to-speech/{vid}", json=payload)
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "audio/mpeg").split(";")[0]
            if not resp.content:
                raise TTSError("ElevenLabs returned empty audio payload")
            return TTSResult(audio=resp.content, content_type=content_type)

        return await call_with_retry(_do, operation="elevenlabs.tts")

    async def aclose(self) -> None:
        await self._client.aclose()


def build_tts_service(settings: Settings | None = None) -> ElevenLabsTTSService:
    s = settings or get_settings()
    return ElevenLabsTTSService(
        api_key=s.elevenlabs_api_key,
        base_url=s.elevenlabs_base_url,
        default_voice_id=s.elevenlabs_voice_id,
        model_id=s.elevenlabs_model_id,
        timeout=s.http_timeout_seconds,
    )
