"""Lazy singleton container for heavy services (dataset, index, models)."""
from __future__ import annotations

import logging
import threading

from .dataset import DatasetStore
from .embeddings import get_embedder
from .gemini import GeminiClient
from .retrieval import Retriever
from .speech import Transcriber
from .tts import LocalSpeechSynthesizer
from .vectorstore import VectorStore
from .websearch import WebSearch

log = logging.getLogger(__name__)


class Services:
    def __init__(self, cfg):
        self.cfg = cfg
        self._lock = threading.Lock()
        self._ready = False
        self.ds: DatasetStore | None = None
        self.embedder = None
        self.store: VectorStore | None = None
        self.retriever: Retriever | None = None
        self.gemini = GeminiClient(cfg["GEMINI_API_KEY"], cfg["GEMINI_MODEL"], cfg["GEMINI_TIMEOUT"])
        self.web = WebSearch(cfg["GOOGLE_CSE_API_KEY"], cfg["GOOGLE_CSE_CX"])
        self.stt = Transcriber(cfg["WHISPER_MODEL"], cfg["WHISPER_DEVICE"], cfg["WHISPER_COMPUTE_TYPE"])
        self.tts = LocalSpeechSynthesizer()

    def ensure_ready(self) -> "Services":
        if self._ready:
            return self
        with self._lock:
            if self._ready:
                return self
            self.ds = DatasetStore(self.cfg["DATASET_PATH"])
            integrity = self.ds.verify_integrity()
            if not integrity["intact"]:
                log.error("DATASET INTEGRITY WARNING: SHA-256 differs from baseline (%s)", integrity)
            self.embedder = get_embedder(self.cfg["EMBEDDING_BACKEND"], self.cfg["EMBEDDING_MODEL"])
            self.store = VectorStore(self.cfg["INDEX_DIR"], self.embedder, self.ds.sha256)
            self.store.ensure(self.ds.df)
            self.retriever = Retriever(self.ds, self.store, self.embedder, self.cfg)
            self._ready = True
            log.info("Services ready: %d records, embedder=%s", len(self.ds), self.embedder.name)
        return self

    def status(self) -> dict:
        d = {"ready": self._ready, "gemini": self.gemini.enabled, "web_search": self.web.enabled,
             "whisper_installed": self.stt.check(), "whisper_model": self.stt.model_name}
        if self._ready:
            d.update(records=len(self.ds), embedder=self.embedder.name, embedder_backend=self.embedder.backend,
                     index=self.store.meta.get("built_at"), integrity=self.ds.verify_integrity())
        return d
