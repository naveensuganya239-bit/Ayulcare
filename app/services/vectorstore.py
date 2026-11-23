"""Persistent FAISS vector store with three views per record.

views
  symptom : "<symptom EN> | <symptom TA>"
  problem : "<problem EN> | <problem TA>"
  full    : symptom + problem + English remedy (+ Tamil symptom/problem)

The index lives in INDEX_DIR, is bound to (dataset sha256, embedding model) via
meta.json and is re-used across requests/restarts. It is rebuilt only when the
dataset or model changes (or when forced with `flask build-index --force`).
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import numpy as np

try:
    import faiss  # type: ignore
    HAVE_FAISS = True
except Exception:  # pragma: no cover
    faiss = None
    HAVE_FAISS = False

log = logging.getLogger(__name__)
VIEWS = ("symptom", "problem", "full")


def _join(*parts: str) -> str:
    return " | ".join(p.strip() for p in parts if p and p.strip())


def view_texts(df) -> dict[str, list[str]]:
    return {
        "symptom": [_join(a, b) for a, b in zip(df["symptom_en"], df["symptom_ta"])],
        "problem": [_join(a, b) for a, b in zip(df["problem_en"], df["problem_ta"])],
        "full": [
            f"Symptom: {_join(se, st)}. Problem: {_join(pe, pt)}. Remedy: {re_.strip()}"
            for se, st, pe, pt, re_ in zip(df["symptom_en"], df["symptom_ta"], df["problem_en"],
                                           df["problem_ta"], df["remedy_en"])
        ],
    }


class VectorStore:
    def __init__(self, index_dir: Path, embedder, dataset_sha: str):
        self.dir = Path(index_dir)
        self.embedder = embedder
        self.sha = dataset_sha
        self.indexes: dict = {}
        self.mats: dict[str, np.ndarray] = {}
        self.ids: list[int] = []
        self.meta: dict = {}

    # ----------------------------------------------------------------- paths
    @property
    def _tag(self) -> str:
        safe = "".join(c if c.isalnum() else "_" for c in self.embedder.name)
        return f"{safe}"

    def _meta_path(self) -> Path:
        return self.dir / f"meta_{self._tag}.json"

    def _view_path(self, view: str) -> Path:
        return self.dir / (f"{view}_{self._tag}.faiss" if HAVE_FAISS else f"{view}_{self._tag}.npy")

    # ----------------------------------------------------------------- build
    def build(self, df) -> dict:
        self.dir.mkdir(parents=True, exist_ok=True)
        t0 = time.time()
        texts = view_texts(df)
        self.ids = [int(x) for x in df["record_id"].tolist()]
        for view in VIEWS:
            vecs = self.embedder.encode(texts[view], kind="passage")
            self.mats[view] = vecs
            if HAVE_FAISS:
                idx = faiss.IndexFlatIP(vecs.shape[1])  # exact inner product == cosine (normalised)
                idx.add(vecs)
                faiss.write_index(idx, str(self._view_path(view)))
                self.indexes[view] = idx
            else:
                np.save(self._view_path(view), vecs)
        self.meta = {
            "dataset_sha256": self.sha, "embedding_backend": self.embedder.backend,
            "embedding_model": self.embedder.name, "dim": int(self.embedder.dim),
            "n_records": len(self.ids), "views": list(VIEWS), "faiss": HAVE_FAISS,
            "record_ids": self.ids, "built_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "build_seconds": round(time.time() - t0, 2),
        }
        self._meta_path().write_text(json.dumps(self.meta), encoding="utf-8")
        log.info("Built vector store (%s records, %.1fs)", len(self.ids), time.time() - t0)
        return self.meta

    # ------------------------------------------------------------------ load
    def load(self) -> bool:
        mp = self._meta_path()
        if not mp.exists():
            return False
        meta = json.loads(mp.read_text(encoding="utf-8"))
        if meta.get("dataset_sha256") != self.sha or meta.get("faiss") != HAVE_FAISS:
            log.warning("Index is stale (dataset/faiss mismatch); rebuild required.")
            return False
        try:
            for view in VIEWS:
                p = self._view_path(view)
                if HAVE_FAISS:
                    idx = faiss.read_index(str(p))
                    self.indexes[view] = idx
                    self.mats[view] = idx.reconstruct_n(0, idx.ntotal)
                else:
                    self.mats[view] = np.load(p)
        except Exception as exc:  # corrupt/missing file
            log.warning("Index load failed: %s", exc)
            return False
        self.meta, self.ids = meta, meta["record_ids"]
        return True

    def ensure(self, df) -> dict:
        if not self.load():
            self.build(df)
        return self.meta

    # ---------------------------------------------------------------- search
    def search(self, view: str, qvecs: np.ndarray, k: int):
        """Top-k per query vector -> (scores[nq,k], positions[nq,k])."""
        k = min(k, len(self.ids))
        if HAVE_FAISS and view in self.indexes:
            return self.indexes[view].search(qvecs.astype("float32"), k)
        sims = qvecs @ self.mats[view].T
        pos = np.argsort(-sims, axis=1)[:, :k]
        return np.take_along_axis(sims, pos, axis=1), pos
