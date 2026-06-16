"""Groq LLM provider (OpenAI-compatible chat completions API)."""

from __future__ import annotations

import httpx

from ..retry import call_with_retry
from .base import LLMError


class GroqLLMService:
    name = "groq"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str,
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
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )

    async def generate(self, prompt: str, *, system_prompt: str) -> str:
        payload = {
            "model": self._model,
            "temperature": self._temperature,
            "max_tokens": self._max_tokens,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
        }

        async def _do() -> str:
            resp = await self._client.post("/chat/completions", json=payload)
            resp.raise_for_status()
            body = resp.json()
            try:
                text = body["choices"][0]["message"]["content"].strip()
            except (KeyError, IndexError, AttributeError) as exc:
                raise LLMError(f"Unexpected Groq response shape: {body!r}") from exc
            if not text:
                raise LLMError("Groq returned an empty response")
            return text

        return await call_with_retry(_do, operation="groq.chat")

    async def aclose(self) -> None:
        await self._client.aclose()
