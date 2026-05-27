"""
core/security.py
────────────────
Speaker enrollment + verification
- เสียง embedding เข้ารหัสด้วย Fernet ก่อนบันทึกลงดิสก์
- Lockout หลัง failed attempts เกินกำหนด
- ไม่บันทึก audio raw ลง disk เด็ดขาด
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
from cryptography.fernet import Fernet
from resemblyzer import VoiceEncoder, preprocess_wav

from config.settings import Settings
from core.logger import get_logger

log = get_logger(__name__)


class SpeakerSecurity:
    """ระบบยืนยันตัวตนผ่านเสียง"""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._sec = settings.security
        self._encoder = VoiceEncoder("cpu")  # ไม่ต้องการ GPU
        self._owner_embedding: np.ndarray | None = None
        self._failed_attempts: int = 0
        self._locked_until: float = 0.0
        self._cipher = self._init_cipher()
        self._load_embedding()
        log.info("speaker_security_ready", enrolled=self.is_enrolled)

    # ── Cipher ───────────────────────────────────────────────────────────

    def _init_cipher(self) -> Fernet:
        """โหลดหรือสร้าง encryption key (เก็บที่ data/security/.key)"""
        key_path = self._settings.cipher_key_path
        if key_path.exists():
            key = key_path.read_bytes()
            log.debug("cipher_key_loaded")
        else:
            key = Fernet.generate_key()
            key_path.parent.mkdir(parents=True, exist_ok=True)
            key_path.write_bytes(key)
            key_path.chmod(0o600)  # owner-only read/write
            log.info("cipher_key_created", path=str(key_path))
        return Fernet(key)

    # ── Persistence ───────────────────────────────────────────────────────

    def _load_embedding(self) -> None:
        path = self._settings.speaker_embedding_path
        if not path.exists():
            return
        try:
            encrypted = path.read_bytes()
            payload = json.loads(self._cipher.decrypt(encrypted))
            self._owner_embedding = np.array(payload["embedding"], dtype=np.float32)
            log.info("speaker_embedding_loaded")
        except Exception as exc:
            log.error("speaker_embedding_load_failed", error=str(exc))

    def _save_embedding(self) -> None:
        if self._owner_embedding is None:
            return
        path = self._settings.speaker_embedding_path
        payload = json.dumps({"embedding": self._owner_embedding.tolist()})
        encrypted = self._cipher.encrypt(payload.encode())
        path.write_bytes(encrypted)
        path.chmod(0o600)
        log.info("speaker_embedding_saved", path=str(path))

    # ── Enrollment ────────────────────────────────────────────────────────

    def enroll(self, audio_samples: list[np.ndarray]) -> bool:
        """
        ลงทะเบียนเสียงเจ้าของบ้าน
        audio_samples: list ของ numpy float32 arrays (sample_rate=16000)
        ต้องการ >= 3 samples เพื่อความแม่นยำ
        """
        if len(audio_samples) < 3:
            log.warning("enroll_insufficient_samples", got=len(audio_samples), required=3)
            return False

        embeddings: list[np.ndarray] = []
        for i, audio in enumerate(audio_samples):
            try:
                wav = preprocess_wav(audio, source_sr=16000)
                emb = self._encoder.embed_utterance(wav)
                embeddings.append(emb)
                log.debug("enroll_sample_ok", index=i)
            except Exception as exc:
                log.warning("enroll_sample_failed", index=i, error=str(exc))

        if len(embeddings) < 3:
            log.error("enroll_failed_too_few_good_samples")
            return False

        # Geometric mean ให้แม่นกว่า arithmetic mean
        self._owner_embedding = np.mean(embeddings, axis=0).astype(np.float32)
        self._owner_embedding /= np.linalg.norm(self._owner_embedding)  # normalize
        self._save_embedding()
        log.info("enroll_success", samples=len(embeddings))
        return True

    def clear_enrollment(self) -> None:
        """ลบข้อมูลเสียงทั้งหมด (สำหรับ re-enroll)"""
        self._owner_embedding = None
        path = self._settings.speaker_embedding_path
        if path.exists():
            path.unlink()
        log.info("enrollment_cleared")

    # ── Verification ──────────────────────────────────────────────────────

    def verify(self, audio: np.ndarray) -> bool:
        """
        ตรวจสอบว่าเสียงนี้เป็นเจ้าของบ้านหรือไม่
        Returns True ถ้าผ่าน หรือถ้ายังไม่ได้ enroll
        """
        # ถ้าปิด verify ใน settings ให้ผ่านเลย
        if not self._sec.verify_speaker:
            return True

        # ยังไม่ enroll → ผ่านเสมอ (development mode)
        if self._owner_embedding is None:
            log.warning("verify_skipped_not_enrolled")
            return True

        # Lockout check
        if time.monotonic() < self._locked_until:
            remaining = int(self._locked_until - time.monotonic())
            log.warning("verify_locked", remaining_seconds=remaining)
            return False

        try:
            wav = preprocess_wav(audio, source_sr=16000)
            embedding = self._encoder.embed_utterance(wav)
            # cosine similarity (ทั้งคู่ normalize แล้ว → dot product ก็พอ)
            similarity = float(np.dot(embedding, self._owner_embedding))

            log.debug("verify_similarity", score=round(similarity, 4))

            if similarity >= self._sec.speaker_threshold:
                self._failed_attempts = 0
                return True
            else:
                self._failed_attempts += 1
                log.warning(
                    "verify_failed",
                    similarity=round(similarity, 4),
                    threshold=self._sec.speaker_threshold,
                    attempts=self._failed_attempts,
                )
                if self._failed_attempts >= self._sec.max_failed_attempts:
                    self._locked_until = (
                        time.monotonic() + self._sec.lockout_duration
                    )
                    self._failed_attempts = 0
                    log.error(
                        "verify_lockout_activated",
                        duration_seconds=self._sec.lockout_duration,
                    )
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
