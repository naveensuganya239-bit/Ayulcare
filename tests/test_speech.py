import io
import wave
from types import SimpleNamespace

import pytest
import torch

from app.services.tts import LocalSpeechSynthesizer


def test_synthesize_returns_mono_wav(monkeypatch):
    class Tokenizer:
        def __call__(self, text, return_tensors):
            assert text == "வணக்கம்"
            assert return_tensors == "pt"
            return {"text": text}

    class Model:
        config = SimpleNamespace(sampling_rate=22050)

        def __call__(self, **tokens):
            assert tokens["text"] == "வணக்கம்"
            return SimpleNamespace(
                waveform=torch.tensor([[0.0, 0.25, -0.25]], dtype=torch.float32)
            )

    synthesizer = LocalSpeechSynthesizer()
    monkeypatch.setattr(synthesizer, "_load", lambda language: (Tokenizer(), Model()))

    result = synthesizer.synthesize("வணக்கம்", "ta")

    with wave.open(io.BytesIO(result), "rb") as wav:
        assert wav.getnchannels() == 1
        assert wav.getsampwidth() == 2
        assert wav.getframerate() == 22050
        assert wav.getnframes() == 3


def test_synthesize_rejects_unsupported_language():
    with pytest.raises(ValueError, match="Unsupported speech language"):
        LocalSpeechSynthesizer().synthesize("hello", "en")
