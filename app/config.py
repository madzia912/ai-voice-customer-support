"""Application configuration loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

LLMProvider = Literal["ollama", "groq", "huggingface"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    public_base_url: str = "http://localhost:8000"

    # Storage
    data_dir: str = "/data"

    # RabbitMQ
    rabbitmq_url: str = "amqp://guest:guest@rabbitmq:5672/"
    rabbitmq_job_queue: str = "voice.jobs"
    rabbitmq_dlx: str = "voice.jobs.dlx"
    rabbitmq_dlq: str = "voice.jobs.dead"
    worker_prefetch: int = 1

    # LLM
    llm_provider: LLMProvider = "ollama"
    llm_max_tokens: int = 512
    llm_temperature: float = 0.7
    llm_system_prompt: str = (
        "You are a concise, friendly customer support voice assistant. "
        "Answer in 1-3 sentences."
    )

    # Ollama
    ollama_base_url: str = "http://ollama:11434"
    ollama_model: str = "llama3.2:1b"

    # Groq
    groq_api_key: str = ""
    groq_model: str = "llama-3.1-8b-instant"
    groq_base_url: str = "https://api.groq.com/openai/v1"

    # HuggingFace
    hf_api_key: str = ""
    hf_model: str = "meta-llama/Llama-3.2-1B-Instruct"

    # ElevenLabs
    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = "21m00Tcm4TlvDq8ikWAM"
    elevenlabs_model_id: str = "eleven_multilingual_v2"
    elevenlabs_base_url: str = "https://api.elevenlabs.io"

    # HTTP / retry
    http_timeout_seconds: float = 60.0
    retry_max_attempts: int = 4
    retry_backoff_base_seconds: float = 1.0

    # Logging
    log_level: str = "INFO"

    @property
    def jobs_dir(self) -> str:
        return f"{self.data_dir.rstrip('/')}/jobs"

    @property
    def audio_dir(self) -> str:
        return f"{self.data_dir.rstrip('/')}/audio"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
