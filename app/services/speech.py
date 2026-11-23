"""Whisper speech-to-text (faster-whisper / CTranslate2 runtime), lazily loaded.

Whisper accuracy for Tamil/Telugu is noticeably lower than for English/Hindi on small models;
use WHISPER_MODEL=small or medium for research use and report per-language WER separately.
"""
from __future__ import annotations

import logging
import os
import tempfile

log = logging.getLogger(__name__)
SUPPORTED_AUDIO = {"audio/webm", "audio/ogg", "audio/wav", "audio/x-wav", "audio/mp4", "audio/mpeg", "audio/m4a", "audio/x-m4a", "video/webm", "audio/aac"}


class Transcriber:
    def __init__(self, model: str, device: str, compute_type: str):
        self.model_name, self.device, self.compute_type = model, device, compute_type
        self._model = None
        self.available: bool | None = None

    def _load(self):
        if self._model is None:
            from faster_whisper import WhisperModel  # lazy
            self._model = WhisperModel(self.model_name, device=self.device, compute_type=self.compute_type)
        return self._model

    def check(self) -> bool:
        if self.available is None:
            try:
                import faster_whisper  # noqa: F401
                self.available = True
            except Exception:
                self.available = False
        return self.available

    def transcribe(self, data: bytes, suffix: str = ".webm", language: str | None = None) -> dict:
        model = self._load()
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
            f.write(data)
            path = f.name
        try:
            segments, info = model.transcribe(path, language=language if language in ("en", "ta", "te", "hi") else None,
                                              vad_filter=True, beam_size=5, condition_on_previous_text=False)
            parts, probs = [], []
            for seg in segments:
                if getattr(seg, "no_speech_prob", 0) > 0.8:
                    continue
                parts.append(seg.text.strip())
                probs.append(seg.avg_logprob)
            text = " ".join(p for p in parts if p).strip()
            return {"text": text, "language": info.language, "language_probability": round(float(info.language_probability), 3),
                    "avg_logprob": round(sum(probs) / len(probs), 3) if probs else None}
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass
