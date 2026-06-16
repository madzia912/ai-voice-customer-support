"""Construct an :class:`LLMService` based on configuration."""

from __future__ import annotations

from ..config import Settings, get_settings
from .base import LLMError, LLMService


def build_llm_service(settings: Settings | None = None) -> LLMService:
    s = settings or get_settings()
    provider = s.llm_provider.lower()

    if provider == "ollama":
        from .ollama import OllamaLLMService

        return OllamaLLMService(
            base_url=s.ollama_base_url,
            model=s.ollama_model,
            timeout=s.http_timeout_seconds,
            temperature=s.llm_temperature,
            max_tokens=s.llm_max_tokens,
        )
    if provider == "groq":
        if not s.groq_api_key:
            raise LLMError("GROQ_API_KEY is required when LLM_PROVIDER=groq")
        from .groq import GroqLLMService

        return GroqLLMService(
            api_key=s.groq_api_key,
            model=s.groq_model,
            base_url=s.groq_base_url,
            timeout=s.http_timeout_seconds,
            temperature=s.llm_temperature,
            max_tokens=s.llm_max_tokens,
        )
    if provider == "huggingface":
        if not s.hf_api_key:
            raise LLMError("HF_API_KEY is required when LLM_PROVIDER=huggingface")
        from .huggingface import HuggingFaceLLMService

        return HuggingFaceLLMService(
            api_key=s.hf_api_key,
            model=s.hf_model,
            timeout=s.http_timeout_seconds,
            temperature=s.llm_temperature,
            max_tokens=s.llm_max_tokens,
        )

    raise LLMError(f"Unknown LLM_PROVIDER: {s.llm_provider}")
