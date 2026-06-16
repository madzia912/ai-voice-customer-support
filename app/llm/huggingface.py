"""HuggingFace Inference API provider (text-generation task)."""

from __future__ import annotations

import httpx

from ..retry import call_with_retry
from .base import LLMError

_BASE_URL = "https://api-inference.huggingface.co/models"


class HuggingFaceLLMService:
    name = "huggingface"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        timeout: float,
        temperature: float,
        max_tokens: int,
    ) -> None:
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._client = httpx.AsyncClient(
            base_url=_BASE_URL,
            timeout=httpx.Timeout(timeout, connect=10.0),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )

    async def generate(self, prompt: str, *, system_prompt: str) -> str:
        # Use a chat-style prompt template that works for most instruct models.
        full_prompt = f"<|system|>\n{system_prompt}\n<|user|>\n{prompt}\n<|assistant|>\n"
        payload = {
            "inputs": full_prompt,
            "parameters": {
                "temperature": self._temperature,
                "max_new_tokens": self._max_tokens,
                "return_full_text": False,
            },
            "options": {"wait_for_model": True},
        }

        async def _do() -> str:
            resp = await self._client.post(f"/{self._model}", json=payload)
            resp.raise_for_status()
            body = resp.json()
            # HF returns a list of dicts for text-generation.
            if isinstance(body, list) and body and "generated_text" in body[0]:
                text = body[0]["generated_text"].strip()
            elif isinstance(body, dict) and "generated_text" in body:
                text = body["generated_text"].strip()
            else:
                raise LLMError(f"Unexpected HuggingFace response shape: {body!r}")
            if not text:
                raise LLMError("HuggingFace returned an empty response")
            return text

        return await call_with_retry(_do, operation="huggingface.generate")

    async def aclose(self) -> None:
        await self._client.aclose()
