"""On-device speech synthesis for Tamil, Telugu, and Hindi."""
from __future__ import annotations

import gc
import io
import re
import threading
import wave

MODEL_IDS = {
    "ta": "facebook/mms-tts-tam",
    "te": "facebook/mms-tts-tel",
    "hi": "facebook/mms-tts-hin",
}
MAX_TEXT_CHARS = 6000
MAX_CHUNK_CHARS = 350


class LocalSpeechSynthesizer:
    def __init__(self):
        self._lock = threading.Lock()
        self._language: str | None = None
        self._tokenizer = None
        self._model = None

    def _load(self, language: str):
        if self._language != language or self._model is None:
            self._language = None
            self._tokenizer = None
            self._model = None
            gc.collect()

            from transformers import AutoTokenizer, VitsModel

            model_id = MODEL_IDS[language]
            self._tokenizer = AutoTokenizer.from_pretrained(model_id)
            self._model = VitsModel.from_pretrained(model_id, use_safetensors=True)
            self._model.eval()
            self._language = language

        return self._tokenizer, self._model

    @staticmethod
    def _chunks(text: str) -> list[str]:
        chunks = []
        current = ""
        for word in text.split():
            if current and len(current) + len(word) + 1 > MAX_CHUNK_CHARS:
                chunks.append(current)
                current = word
            else:
                current = f"{current} {word}".strip()
        if current:
            chunks.append(current)
        return chunks

    def synthesize(self, text: str, language: str) -> bytes:
        if language not in MODEL_IDS:
            raise ValueError("Unsupported speech language.")

        text = " ".join((text or "").split())
        if not text:
            raise ValueError("Speech text is required.")
        if len(text) > MAX_TEXT_CHARS:
            raise ValueError(f"Speech text must be {MAX_TEXT_CHARS} characters or fewer.")

        import numpy as np
        import torch

        with self._lock:
            tokenizer, model = self._load(language)
            audio_chunks = []
            with torch.inference_mode():
                for chunk in self._chunks(text):
                    tokens = tokenizer(chunk, return_tensors="pt")
                    waveform = model(**tokens).waveform[0].cpu().numpy()
                    audio_chunks.append(waveform.astype(np.float32, copy=False))

            sample_rate = int(model.config.sampling_rate)
            silence = np.zeros(int(sample_rate * 0.12), dtype=np.float32)
            joined = []
            for index, chunk in enumerate(audio_chunks):
                if index:
                    joined.append(silence)
                joined.append(chunk)
            audio = np.concatenate(joined)

        pcm = (np.clip(audio, -1.0, 1.0) * 32767).astype("<i2")
        output = io.BytesIO()
        with wave.open(output, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)
            wav.writeframes(pcm.tobytes())
        return output.getvalue()
