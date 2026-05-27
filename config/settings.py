"""
config/settings.py
─────────────────
Centralized configuration via Pydantic-Settings.
ทุก config โหลดจาก .env → environment variables → defaults
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# ── Sub-settings ───────────────────────────────────────────────────────────

class AudioSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AUDIO__",
        env_file=".env",
        env_ignore_empty=True,
        extra="ignore",
    )

    sample_rate: int = 16000
    chunk_size: int = 1024
    silence_threshold: float = Field(0.02, ge=0.001, le=0.5)
    silence_duration: float = Field(1.5, ge=0.5, le=5.0)
    device_index: int | None = None  # None = ใช้ default mic


class LLMSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="LLM__",
        env_file=".env",
        env_ignore_empty=True,
        extra="ignore",
    )

    model: str = "llama3.2:3b"
    base_url: str = "http://localhost:11434"
    temperature: float = Field(0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(512, ge=64, le=4096)
    context_window: int = 4096
    timeout: int = 60  # seconds


class SecuritySettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SECURITY__",
        env_file=".env",
        env_ignore_empty=True,
        extra="ignore",
    )

    speaker_threshold: float = Field(0.82, ge=0.5, le=1.0)
    max_failed_attempts: int = Field(3, ge=1, le=10)
    lockout_duration: int = Field(60, ge=10, le=3600)  # seconds
    verify_speaker: bool = True


class TTSSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="TTS__",
        env_file=".env",
        env_ignore_empty=True,
        extra="ignore",
    )

    engine: Literal["macos", "kokoro"] = "macos"
    voice: str = "Kanya"  # macOS Thai voice
    rate: int = Field(185, ge=80, le=350)


class WakeWordSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="WAKE_WORD__",
        env_file=".env",
        env_ignore_empty=True,
        extra="ignore",
    )

    phrase: str = "hey jarvis"
    threshold: float = Field(0.5, ge=0.1, le=1.0)
    enabled: bool = True


class MemorySettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MEMORY__",
        env_file=".env",
        env_ignore_empty=True,
        extra="ignore",
    )

    max_history: int = Field(20, ge=5, le=100)
    persist_dir: Path = Path("data/memory")


# ── Root Settings ──────────────────────────────────────────────────────────

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_nested_delimiter="__",
        env_ignore_empty=True,
        case_sensitive=False,
        extra="ignore",
    )

    # Identity
    assistant_name: str = "Jarvis"
    language: str = "th"
    debug: bool = False

    # Paths
    data_dir: Path = Path("data")
    logs_dir: Path = Path("data/logs")

    # Sub-settings (ใช้ __  delimiter)
    audio: AudioSettings = Field(default_factory=AudioSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)
    tts: TTSSettings = Field(default_factory=TTSSettings)
    wake_word: WakeWordSettings = Field(default_factory=WakeWordSettings)
    memory: MemorySettings = Field(default_factory=MemorySettings)

    # Optional integrations
    gmail_credentials_path: Path | None = None
    searxng_url: str = "http://localhost:8888"

    @model_validator(mode="after")
    def create_directories(self) -> "Settings":
        """สร้าง directory ที่จำเป็นอัตโนมัติตอน boot"""
        dirs = [
            self.data_dir,
            self.logs_dir,
            self.data_dir / "security",
            self.memory.persist_dir,
        ]
        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)
        return self

    @field_validator("language")
    @classmethod
    def validate_language(cls, v: str) -> str:
        supported = {"th", "en", "ja", "zh"}
        if v not in supported:
            raise ValueError(f"language must be one of {supported}")
        return v

    @field_validator("debug", mode="before")
    @classmethod
    def parse_debug(cls, v: Any) -> bool:
        if isinstance(v, str):
            normalized = v.strip().lower()
            if normalized in {"release", "prod", "production", "false", "0", "no", "off"}:
                return False
            if normalized in {"debug", "dev", "development", "true", "1", "yes", "on"}:
                return True
        return v

    @property
    def speaker_embedding_path(self) -> Path:
        return self.data_dir / "security" / "speaker.enc"

    @property
    def cipher_key_path(self) -> Path:
        return self.data_dir / "security" / ".key"


# Singleton — import และใช้ได้เลยทุกที่
settings = Settings()
