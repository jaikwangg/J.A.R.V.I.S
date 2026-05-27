"""
services/wake_word.py
─────────────────────
Wake word detection — "Hey Jarvis" / คำที่กำหนดเอง
- ใช้ openwakeword (ถ้าติดตั้ง) หรือ fallback ไป energy threshold
- รัน background thread ไม่ block main loop
"""
from __future__ import annotations

import threading
from typing import Callable

import numpy as np

from config.settings import Settings
from core.logger import get_logger

log = get_logger(__name__)


class WakeWordDetector:
    """
    ฟังคำปลุกและ callback เมื่อได้ยิน
    Usage:
        detector = WakeWordDetector(settings)
        detector.start(on_detected=lambda: print("Heard wake word!"))
        ...
        detector.stop()
    """

    def __init__(self, settings: Settings) -> None:
        self._cfg = settings.wake_word
        self._audio_cfg = settings.audio
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._model = self._load_model()

    def _load_model(self):
        """โหลด openwakeword model ถ้าติดตั้งไว้"""
        try:
            from openwakeword.model import Model  # type: ignore[import]
            model = Model(inference_framework="onnx")
            log.info("wake_word_openwakeword_loaded")
            return model
        except ImportError:
            log.warning(
                "wake_word_openwakeword_not_installed",
                fallback="energy_threshold",
                install="pip install openwakeword",
            )
            return None

    def _detect_openwakeword(
        self, chunk: np.ndarray, on_detected: Callable
    ) -> None:
        """ใช้ openwakeword model"""
        self._model.predict(chunk)
        scores: dict = self._model.prediction_buffer
        for phrase, score_arr in scores.items():
            if score_arr and max(score_arr) > self._cfg.threshold:
                log.info("wake_word_detected", phrase=phrase, score=max(score_arr))
                on_detected()
                self._model.reset()  # clear buffer หลัง detect
                break

    def _detect_energy(self, chunk: np.ndarray, on_detected: Callable) -> None:
        """Fallback: ตรวจจับเสียงดังกว่า threshold"""
        energy = float(np.abs(chunk).mean())
        if energy > self._audio_cfg.silence_threshold * 3:
            log.debug("wake_word_energy_trigger", energy=round(energy, 4))
            on_detected()

    def start(self, on_detected: Callable[[], None]) -> None:
        """เริ่ม background thread ฟังคำปลุก"""
        if not self._cfg.enabled:
            log.info("wake_word_disabled")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            args=(on_detected,),
            daemon=True,
            name="wake-word-listener",
        )
        self._thread.start()
        log.info("wake_word_listening", phrase=self._cfg.phrase)

    def _run(self, on_detected: Callable) -> None:
        import queue
        import sounddevice as sd

        q: queue.Queue[np.ndarray] = queue.Queue()

        def cb(indata, frames, time_info, status):
            q.put(indata.copy().flatten())

        with sd.InputStream(
            samplerate=self._audio_cfg.sample_rate,
            channels=1,
            blocksize=self._audio_cfg.chunk_size,
            callback=cb,
            dtype="float32",
        ):
            while not self._stop_event.is_set():
                try:
                    chunk = q.get(timeout=1.0)
                    if self._model is not None:
                        self._detect_openwakeword(chunk, on_detected)
                    else:
                        self._detect_energy(chunk, on_detected)
                except queue.Empty:
                    continue
                except Exception as exc:
                    log.error("wake_word_error", error=str(exc))

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2.0)
        log.info("wake_word_stopped")
