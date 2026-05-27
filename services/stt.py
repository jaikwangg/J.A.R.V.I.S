"""
services/stt.py
───────────────
Speech-to-Text ผ่าน faster-whisper
- รัน local 100% (ไม่ส่งเสียงออก internet)
- ใช้ CoreML/Metal บน Apple Silicon ผ่าน int8 quantization
- รองรับภาษาไทยและอื่นๆ
"""
from __future__ import annotations

import numpy as np
from faster_whisper import WhisperModel

from config.settings import Settings
from core.logger import get_logger

log = get_logger(__name__)

# Model size → tradeoff speed vs accuracy
# tiny  : เร็วมาก, แม่นน้อย  (~39MB)
# base  : เร็ว, ใช้ได้        (~74MB)
# small : แนะนำสำหรับ M1+    (~244MB)
# medium: แม่นมาก, ช้ากว่า   (~769MB)
_RECOMMENDED_MODEL = "small"


class STTService:
    """Whisper Speech-to-Text wrapper"""

    def __init__(self, settings: Settings, model_size: str = _RECOMMENDED_MODEL) -> None:
        self._language = settings.language
        log.info("stt_loading_model", model=model_size)
        self._model = WhisperModel(
            model_size,
            device="auto",        # auto-detects Metal/CPU
            compute_type="int8",  # ประหยัด memory, เร็วบน Apple Silicon
        )
        log.info("stt_model_ready", model=model_size, language=self._language)

    def transcribe(self, audio: np.ndarray) -> str:
        """
        แปลง audio เป็น text
        audio: float32 numpy array, 16kHz, mono
        Returns: transcribed text (stripped)
        """
        if len(audio) == 0:
            return ""

        segments, info = self._model.transcribe(
            audio,
            language=self._language,
            beam_size=5,
            vad_filter=True,          # กรอง silence ด้วย built-in VAD
            vad_parameters={
                "min_silence_duration_ms": 500,
                "speech_pad_ms": 200,
            },
            condition_on_previous_text=False,  # ลด hallucination
        )

        text = " ".join(seg.text.strip() for seg in segments).strip()
        log.debug(
            "stt_transcribed",
            language=info.language,
            confidence=round(info.language_probability, 3),
            text_preview=text[:80],
        )
        return text

    def transcribe_file(self, path: str) -> str:
        """แปลง audio file เป็น text (สำหรับ testing)"""
        segments, _ = self._model.transcribe(path, language=self._language)
        return " ".join(seg.text.strip() for seg in segments).strip()
