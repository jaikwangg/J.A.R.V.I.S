"""Tests for SpeakerSecurity (no mic needed)"""
import numpy as np
import pytest
from config.settings import Settings
from core.security import SpeakerSecurity


@pytest.fixture
def sec(tmp_path):
    s = Settings(
        data_dir=tmp_path / "data",
        logs_dir=tmp_path / "logs",
        memory_persist_dir=tmp_path / "memory",
        security_verify_speaker=True,
    )
    return SpeakerSecurity(s)


def test_not_enrolled_initially(sec):
    assert not sec.is_enrolled


def test_verify_passes_when_not_enrolled(sec):
    dummy = np.zeros(16000, dtype=np.float32)
    assert sec.verify(dummy) is True  # skips verify if not enrolled


def test_verify_passes_when_disabled(tmp_path):
    s = Settings(
        data_dir=tmp_path / "data",
        logs_dir=tmp_path / "logs",
        memory_persist_dir=tmp_path / "memory",
        security_verify_speaker=False,
    )
    sec = SpeakerSecurity(s)
    assert sec.verify(np.zeros(16000, dtype=np.float32)) is True


def test_cipher_key_created(sec):
    assert sec._settings.cipher_key_path.exists()


def test_enroll_requires_min_samples(sec):
    samples = [np.random.randn(16000).astype(np.float32) for _ in range(2)]
    result = sec.enroll(samples)
    assert result is False  # need >= 3
