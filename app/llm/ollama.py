"""Ollama LLM provider (https://github.com/ollama/ollama)."""

from __future__ import annotations

import httpx

from ..retry import call_with_retry
from .base import LLMError


class OllamaLLMService:
    name = "ollama"

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        timeout: float,
        temperature: float,
        max_tokens: int,
    ) -> None:
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=httpx.Timeout(timeout, connect=10.0),
        )

    async def generate(self, prompt: str, *, system_prompt: str) -> str:
        payload = {
            "model": self._model,
            "stream": False,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            "options": {
                "temperature": self._temperature,
                "num_predict": self._max_tokens,
            },
        }

        async def _do() -> str:
            resp = await self._client.post("/api/chat", json=payload)
            resp.raise_for_status()
            body = resp.json()
            message = body.get("message") or {}
            text = (message.get("content") or "").strip()
            if not text:
                raise LLMError("Ollama returned an empty response")
            return text

        return await call_with_retry(_do, operation="ollama.chat")

    async def aclose(self) -> None:
        await self._client.aclose()
