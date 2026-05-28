"""
config/settings.py
─────────────────
Centralized configuration via Pydantic-Settings v2
โหลดจาก .env → environment → defaults
"""
from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Single flat settings class — ง่ายกว่าและไม่มี env_prefix ซ้อน
    ทุก key โหลดจาก .env ตรงๆ
    """
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Identity ──────────────────────────────────────────────────────────
    assistant_name: str = "Jarvis"
    language: str = "th"
    debug: bool = False

    # ── Paths ─────────────────────────────────────────────────────────────
    data_dir: Path = Path("data")
    logs_dir: Path = Path("data/logs")

    # ── LLM ───────────────────────────────────────────────────────────────
    llm_model: str = "llama3.2:3b"
    llm_base_url: str = "http://localhost:11434"
    llm_temperature: float = Field(0.7, ge=0.0, le=2.0)
    llm_max_tokens: int = Field(512, ge=64, le=4096)
    llm_timeout: int = 60

    # ── Audio ─────────────────────────────────────────────────────────────
    audio_sample_rate: int = 16000
    audio_chunk_size: int = 1024
    audio_silence_threshold: float = Field(0.02, ge=0.001, le=0.5)
    audio_silence_duration: float = Field(1.5, ge=0.5, le=5.0)
    audio_device_index: int | None = None

    # ── Wake Word ─────────────────────────────────────────────────────────
    wake_word_phrase: str = "hey jarvis"
    wake_word_threshold: float = Field(0.5, ge=0.1, le=1.0)
    wake_word_enabled: bool = True

    # ── Security ──────────────────────────────────────────────────────────
    security_speaker_threshold: float = Field(0.82, ge=0.5, le=1.0)
    security_max_failed_attempts: int = Field(3, ge=1, le=10)
    security_lockout_duration: int = Field(60, ge=10, le=3600)
    security_verify_speaker: bool = True

    # ── TTS ───────────────────────────────────────────────────────────────
    tts_engine: Literal["macos", "kokoro"] = "macos"
    tts_voice: str = "Kanya"
    tts_rate: int = Field(185, ge=80, le=350)

    # ── Memory ────────────────────────────────────────────────────────────
    memory_max_history: int = Field(20, ge=5, le=100)
    memory_persist_dir: Path = Path("data/memory")

    # ── Integrations ──────────────────────────────────────────────────────
    gmail_credentials_path: Path | None = None
    searxng_url: str = "http://localhost:8888"

    # ── Validators ────────────────────────────────────────────────────────

    @field_validator("language")
    @classmethod
    def validate_language(cls, v: str) -> str:
        supported = {"th", "en", "ja", "zh"}
        if v not in supported:
            raise ValueError(f"language must be one of {supported}")
        return v

    @model_validator(mode="after")
    def create_directories(self) -> "Settings":
        """สร้าง directories ที่จำเป็นอัตโนมัติ"""
        for d in [
            self.data_dir,
            self.logs_dir,
            self.data_dir / "security",
            self.memory_persist_dir,
        ]:
            d.mkdir(parents=True, exist_ok=True)
        return self

    # ── Computed paths ────────────────────────────────────────────────────

    @property
    def speaker_embedding_path(self) -> Path:
        return self.data_dir / "security" / "speaker.enc"

    @property
    def cipher_key_path(self) -> Path:
        return self.data_dir / "security" / ".key"


# Singleton
settings = Settings()
