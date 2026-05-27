"""
services/tts.py
───────────────
Text-to-Speech abstraction
- macOS engine : ใช้ `say` command built-in (ไม่ต้องติดตั้งเพิ่ม)
- Kokoro engine: คุณภาพสูงกว่า, ต้องติดตั้ง kokoro-onnx
"""
from __future__ import annotations

import subprocess
from abc import ABC, abstractmethod

from config.settings import Settings
from core.logger import get_logger

log = get_logger(__name__)


# ── Base ──────────────────────────────────────────────────────────────────

class BaseTTS(ABC):
    @abstractmethod
    def speak(self, text: str, blocking: bool = True) -> None: ...

    @abstractmethod
    def stop(self) -> None: ...


# ── macOS engine ──────────────────────────────────────────────────────────

class MacOSTTS(BaseTTS):
    """
    ใช้ macOS `say` command — ฟรี, ไม่ต้องติดตั้งเพิ่ม
    ภาษาไทย: Kanya (หญิง), Narisa (หญิง)
    ภาษาอังกฤษ: Samantha, Alex, Ava ฯลฯ
    ดู voices ทั้งหมด: `say -v ?`
    """

    def __init__(self, settings: Settings) -> None:
        self._voice = settings.tts.voice
        self._rate = settings.tts.rate
        self._proc: subprocess.Popen | None = None
        log.info("tts_macos_ready", voice=self._voice, rate=self._rate)

    def speak(self, text: str, blocking: bool = True) -> None:
        if not text.strip():
            return
        self.stop()  # หยุดเสียงก่อนหน้า
        cmd = ["say", "-v", self._voice, "-r", str(self._rate), text]
        log.debug("tts_speak", engine="macos", chars=len(text))
        if blocking:
            subprocess.run(cmd, check=False)
        else:
            self._proc = subprocess.Popen(cmd)

    def stop(self) -> None:
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            self._proc = None
        subprocess.run(["killall", "say"], capture_output=True)


# ── Kokoro engine ─────────────────────────────────────────────────────────

class KokoroTTS(BaseTTS):
    """
    Kokoro ONNX TTS — คุณภาพสูงกว่า macOS say
    ติดตั้ง: pip install kokoro-onnx
    """

    def __init__(self, settings: Settings) -> None:
        try:
            from kokoro_onnx import Kokoro  # type: ignore[import]
            import sounddevice as sd
            import soundfile as sf

            self._kokoro = Kokoro("kokoro-v0_19.onnx", "voices.bin")
            self._sd = sd
            self._sf = sf
            self._voice = settings.tts.voice
            log.info("tts_kokoro_ready", voice=self._voice)
        except ImportError:
            raise RuntimeError(
                "Kokoro not installed. Run: pip install kokoro-onnx soundfile"
            )

    def speak(self, text: str, blocking: bool = True) -> None:
        if not text.strip():
            return
        samples, sr = self._kokoro.create(text, voice=self._voice, speed=1.0, lang="th")
        log.debug("tts_speak", engine="kokoro", chars=len(text))
        self._sd.play(samples, samplerate=sr)
        if blocking:
            self._sd.wait()

    def stop(self) -> None:
        try:
            import sounddevice as sd
            sd.stop()
        except Exception:
            pass


# ── Factory ───────────────────────────────────────────────────────────────

def create_tts(settings: Settings) -> BaseTTS:
    engine = settings.tts.engine
    if engine == "kokoro":
        try:
            return KokoroTTS(settings)
        except RuntimeError as e:
            log.warning("tts_kokoro_fallback", reason=str(e))
    return MacOSTTS(settings)
