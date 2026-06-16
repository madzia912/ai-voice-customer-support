"""Provider selection + missing-credential errors for the LLM factory."""

from __future__ import annotations

import pytest

from app.llm import LLMError, build_llm_service


def test_ollama_is_selected_by_default(settings_env) -> None:
    svc = build_llm_service()
    assert svc.name == "ollama"


def test_groq_requires_api_key(monkeypatch: pytest.MonkeyPatch, settings_env) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    from app.config import get_settings

    get_settings.cache_clear()

    with pytest.raises(LLMError, match="GROQ_API_KEY"):
        build_llm_service()


def test_huggingface_requires_api_key(
    monkeypatch: pytest.MonkeyPatch, settings_env
) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "huggingface")
    from app.config import get_settings

    get_settings.cache_clear()

    with pytest.raises(LLMError, match="HF_API_KEY"):
        build_llm_service()


def test_groq_builds_when_key_present(
    monkeypatch: pytest.MonkeyPatch, settings_env
) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "gk-test")
    from app.config import get_settings

    get_settings.cache_clear()

    svc = build_llm_service()
    assert svc.name == "groq"
