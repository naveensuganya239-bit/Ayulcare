"""Embedding back-ends.

* SentenceTransformerEmbedder -- the research/production back-end (multilingual).
* HashingEmbedder             -- dependency-free character-n-gram fallback used ONLY for
                                 offline development and automated tests. It is lexical,
                                 NOT cross-lingual, and must never be used for reported results.
"""
from __future__ import annotations

import re
import unicodedata
import zlib

import numpy as np


class BaseEmbedder:
    name: str = "base"
    backend: str = "base"
    dim: int = 0

    def encode(self, texts: list[str], kind: str = "passage") -> np.ndarray:  # pragma: no cover
        raise NotImplementedError


class SentenceTransformerEmbedder(BaseEmbedder):
    backend = "sentence-transformers"

    def __init__(self, model_name: str):
        from sentence_transformers import SentenceTransformer  # lazy: heavy import

        self.name = model_name
        self.model = SentenceTransformer(model_name)
        self.dim = int(self.model.get_sentence_embedding_dimension())
        self._e5 = "e5" in model_name.lower()

    def encode(self, texts: list[str], kind: str = "passage") -> np.ndarray:
        if self._e5:  # E5 models require instruction prefixes
            prefix = "query: " if kind == "query" else "passage: "
            texts = [prefix + t for t in texts]
        vecs = self.model.encode(texts, batch_size=64, normalize_embeddings=True,
                                 show_progress_bar=len(texts) > 500, convert_to_numpy=True)
        return vecs.astype("float32")


class HashingEmbedder(BaseEmbedder):
    backend = "hash"
    name = "hashing-char-ngram-512"
    dim = 512

    def __init__(self, dim: int = 512):
        self.dim = dim

    @staticmethod
    def _tokens(text: str) -> list[str]:
        text = unicodedata.normalize("NFKC", text).lower()
        words = re.findall(r"\w+", text, flags=re.UNICODE)
        feats: list[str] = []
        for w in words:
            feats.append("w:" + w)
            padded = f"^{w}$"
            for n in (3, 4):
                feats.extend("c:" + padded[i:i + n] for i in range(max(1, len(padded) - n + 1)))
        return feats

    def encode(self, texts: list[str], kind: str = "passage") -> np.ndarray:
        out = np.zeros((len(texts), self.dim), dtype="float32")
        for r, t in enumerate(texts):
            for f in self._tokens(t):
                h = zlib.crc32(f.encode("utf-8"))
                out[r, h % self.dim] += 1.0
        out = np.sqrt(out)  # sub-linear tf
        norms = np.linalg.norm(out, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return (out / norms).astype("float32")


_CACHE: dict[tuple, BaseEmbedder] = {}


def get_embedder(backend: str, model_name: str) -> BaseEmbedder:
    key = (backend, model_name)
    if key not in _CACHE:
        _CACHE[key] = HashingEmbedder() if backend == "hash" else SentenceTransformerEmbedder(model_name)
    return _CACHE[key]
