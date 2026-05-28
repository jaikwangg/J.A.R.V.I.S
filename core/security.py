"""
core/security.py
────────────────
Speaker enrollment + verification
- Embedding เข้ารหัส Fernet ก่อนบันทึกลง disk
- Lockout หลัง failed attempts เกินกำหนด
- ไม่บันทึก raw audio ลง disk เด็ดขาด
"""
from __future__ import annotations

import json
import time

import numpy as np
from cryptography.fernet import Fernet
from resemblyzer import VoiceEncoder, preprocess_wav

from config.settings import Settings
from core.logger import get_logger

log = get_logger(__name__)


class SpeakerSecurity:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._encoder = VoiceEncoder("cpu")
        self._owner_embedding: np.ndarray | None = None
        self._failed_attempts: int = 0
        self._locked_until: float = 0.0
        self._cipher = self._init_cipher()
        self._load_embedding()
        log.info("speaker_security_ready", enrolled=self.is_enrolled)

    def _init_cipher(self) -> Fernet:
        key_path = self._settings.cipher_key_path
        if key_path.exists():
            return Fernet(key_path.read_bytes())
        key = Fernet.generate_key()
        key_path.parent.mkdir(parents=True, exist_ok=True)
        key_path.write_bytes(key)
        key_path.chmod(0o600)
        log.info("cipher_key_created")
        return Fernet(key)

    def _load_embedding(self) -> None:
        path = self._settings.speaker_embedding_path
        if not path.exists():
            return
        try:
            payload = json.loads(self._cipher.decrypt(path.read_bytes()))
            self._owner_embedding = np.array(payload["embedding"], dtype=np.float32)
            log.info("speaker_embedding_loaded")
        except Exception as exc:
            log.error("speaker_embedding_load_failed", error=str(exc))

    def _save_embedding(self) -> None:
        if self._owner_embedding is None:
            return
        path = self._settings.speaker_embedding_path
        encrypted = self._cipher.encrypt(
            json.dumps({"embedding": self._owner_embedding.tolist()}).encode()
        )
        path.write_bytes(encrypted)
        path.chmod(0o600)
        log.info("speaker_embedding_saved")

    def enroll(self, audio_samples: list[np.ndarray]) -> bool:
        if len(audio_samples) < 3:
            log.warning("enroll_insufficient_samples", got=len(audio_samples), required=3)
            return False

        embeddings = []
        for i, audio in enumerate(audio_samples):
            try:
                wav = preprocess_wav(audio, source_sr=16000)
                embeddings.append(self._encoder.embed_utterance(wav))
                log.debug("enroll_sample_ok", index=i)
            except Exception as exc:
                log.warning("enroll_sample_failed", index=i, error=str(exc))

        if len(embeddings) < 3:
            log.error("enroll_failed_too_few_good_samples")
            return False

        emb = np.mean(embeddings, axis=0).astype(np.float32)
        self._owner_embedding = emb / np.linalg.norm(emb)
        self._save_embedding()
        log.info("enroll_success", samples=len(embeddings))
        return True

    def clear_enrollment(self) -> None:
        self._owner_embedding = None
        p = self._settings.speaker_embedding_path
        if p.exists():
            p.unlink()
        log.info("enrollment_cleared")

    def verify(self, audio: np.ndarray) -> bool:
        if not self._settings.security_verify_speaker:
            return True
        if self._owner_embedding is None:
            log.warning("verify_skipped_not_enrolled")
            return True
        if time.monotonic() < self._locked_until:
            log.warning("verify_locked", remaining=int(self._locked_until - time.monotonic()))
            return False
        try:
            wav = preprocess_wav(audio, source_sr=16000)
            emb = self._encoder.embed_utterance(wav)
            similarity = float(np.dot(emb, self._owner_embedding))
            log.debug("verify_similarity", score=round(similarity, 4))

            if similarity >= self._settings.security_speaker_threshold:
                self._failed_attempts = 0
                return True

            self._failed_attempts += 1
            log.warning("verify_failed", similarity=round(similarity, 4), attempts=self._failed_attempts)
            if self._failed_attempts >= self._settings.security_max_failed_attempts:
                self._locked_until = time.monotonic() + self._settings.security_lockout_duration
                self._failed_attempts = 0
                log.error("verify_lockout_activated", duration=self._settings.security_lockout_duration)
            return False
        except Exception as exc:
            log.error("verify_error", error=str(exc))
            return False

    @property
    def is_enrolled(self) -> bool:
        return self._owner_embedding is not None

    @property
    def is_locked(self) -> bool:
        return time.monotonic() < self._locked_until
