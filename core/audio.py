"""
core/audio.py
─────────────
Audio I/O pipeline
- Record จาก microphone จนกว่าจะเงียบ (VAD-based)
- Energy-based VAD — ไม่ต้องการ model เพิ่ม
- ไม่บันทึก audio ลง disk (privacy-first)
"""
from __future__ import annotations

import queue
import threading
from typing import Callable

import numpy as np
import sounddevice as sd

from config.settings import Settings
from core.logger import get_logger

log = get_logger(__name__)


class AudioCapture:
    """
    Record audio จาก microphone
    - record_utterance()  : รอจนกว่าจะเงียบ → return numpy array
    - stream_chunks()     : generator ส่ง chunk ต่อเนื่อง (สำหรับ wake word)
    """

    def __init__(self, settings: Settings) -> None:
        self._cfg = settings.audio
        self._q: queue.Queue[np.ndarray] = queue.Queue()
        self._stop_event = threading.Event()
        log.info(
            "audio_capture_init",
            sample_rate=self._cfg.sample_rate,
            device=self._cfg.device_index,
        )

    # ── Callback ──────────────────────────────────────────────────────────

    def _callback(
        self,
        indata: np.ndarray,
        frames: int,
        time_info: object,
        status: sd.CallbackFlags,
    ) -> None:
        if status:
            log.debug("audio_callback_status", status=str(status))
        self._q.put(indata.copy().flatten())

    # ── VAD ───────────────────────────────────────────────────────────────

    def _is_silent(self, chunk: np.ndarray) -> bool:
        return float(np.abs(chunk).mean()) < self._cfg.silence_threshold

    # ── Public API ────────────────────────────────────────────────────────

    def record_utterance(self, max_duration: float = 30.0) -> np.ndarray | None:
        """
        เริ่มฟังเมื่อมีเสียง หยุดเมื่อเงียบ silence_duration วินาที
        Returns: float32 numpy array (16kHz mono) หรือ None ถ้าไม่มีเสียง
        """
        sr = self._cfg.sample_rate
        chunk = self._cfg.chunk_size
        silence_chunks_needed = int(
            self._cfg.silence_duration * sr / chunk
        )
        max_chunks = int(max_duration * sr / chunk)

        chunks: list[np.ndarray] = []
        silent_chunks = 0
        speaking = False
        total_chunks = 0

        while not self._q.empty():
            self._q.get_nowait()  # flush stale audio

        with sd.InputStream(
            samplerate=sr,
            channels=1,
            blocksize=chunk,
            callback=self._callback,
            dtype="float32",
            device=self._cfg.device_index,
        ):
            log.debug("audio_listening_started")
            while total_chunks < max_chunks:
                try:
                    data = self._q.get(timeout=2.0)
                except queue.Empty:
                    break

                total_chunks += 1
                silent = self._is_silent(data)

                if not silent:
                    speaking = True
                    silent_chunks = 0
                    chunks.append(data)
                elif speaking:
                    chunks.append(data)
                    silent_chunks += 1
                    if silent_chunks >= silence_chunks_needed:
                        break

        if not chunks or not speaking:
            log.debug("audio_no_speech_detected")
            return None

        audio = np.concatenate(chunks, dtype=np.float32)
        duration = len(audio) / sr
        log.debug("audio_utterance_captured", duration_s=round(duration, 2))
        return audio

    def stream_chunks(
        self,
        on_chunk: Callable[[np.ndarray], None],
        stop_event: threading.Event | None = None,
    ) -> None:
        """
        Stream audio chunks ต่อเนื่อง (สำหรับ wake word detection)
        หยุดเมื่อ stop_event ถูก set
        """
        sr = self._cfg.sample_rate
        chunk = self._cfg.chunk_size
        _stop = stop_event or threading.Event()

        with sd.InputStream(
            samplerate=sr,
            channels=1,
            blocksize=chunk,
            callback=self._callback,
            dtype="float32",
            device=self._cfg.device_index,
        ):
            log.info("audio_stream_started")
            while not _stop.is_set():
                try:
                    data = self._q.get(timeout=0.5)
                    on_chunk(data)
                except queue.Empty:
                    continue
            log.info("audio_stream_stopped")

    @staticmethod
    def list_devices() -> list[dict]:
        """แสดง microphone ที่มีทั้งหมด"""
        devices = sd.query_devices()
        result = []
        for i, d in enumerate(devices):  # type: ignore[arg-type]
            if d["max_input_channels"] > 0:
                result.append({"index": i, "name": d["name"]})
        return result
