"""Smoke tests — settings, memory, security (no hardware needed)"""
import pytest
from pathlib import Path
from config.settings import Settings


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path / "data",
        logs_dir=tmp_path / "logs",
        memory_persist_dir=tmp_path / "memory",
        debug=True,
    )


def test_settings_defaults(tmp_path):
    s = make_settings(tmp_path)
    assert s.assistant_name == "Jarvis"
    assert s.language == "th"
    assert s.llm_model == "llama3.2:3b"


def test_settings_directories_created(tmp_path):
    s = make_settings(tmp_path)
    assert s.data_dir.exists()
    assert s.logs_dir.exists()
    assert (s.data_dir / "security").exists()


def test_settings_invalid_language(tmp_path):
    with pytest.raises(Exception):
        Settings(data_dir=tmp_path, logs_dir=tmp_path, language="xx")


def test_cipher_key_path(tmp_path):
    s = make_settings(tmp_path)
    assert s.cipher_key_path == s.data_dir / "security" / ".key"
    assert s.speaker_embedding_path == s.data_dir / "security" / "speaker.enc"
