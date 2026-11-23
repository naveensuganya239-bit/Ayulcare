"""Symptom-aware retrieval over the Ayurvedic dataset.

Three retrieval modes are implemented for the IEEE comparison:

  problem_only : Baseline 1 - match the query to PROBLEM names only, then return that
                 problem's records in dataset order (what a naive keyword/problem
                 lookup does; the choice among multiple remedies is arbitrary).
  symptom_rag  : Baseline 2 - FAISS semantic retrieval ranked by weighted symptom /
                 full-text / problem similarity. No thresholds, no filters.
  proposed     : Symptom-aware retrieval + problem-group symptom coverage +
                 relevance thresholds + safety filtering + remedy diversification.

Similarity scores are *ranking signals only*. They are never medical confidence.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import numpy as np

# Defaults per embedding back-end. Cosine ranges differ strongly between models
# (E5 scores are compressed into ~0.7-1.0), so these MUST be calibrated:
#   flask calibrate-thresholds
DEFAULT_THRESHOLDS = {
    "hash": {"symptom": 0.40, "full": 0.32},
    "sentence-transformers": {"symptom": 0.84, "full": 0.80},
}

CONDITION_TERMS = {
    "pregnancy": r"pregnan|gestation|expectant",
    "diabetes": r"diabet|blood sugar",
    "hypertension": r"hypertens|high blood pressure|blood pressure",
    "heart": r"heart|cardiac|cardio",
    "kidney": r"kidney|renal|nephr",
    "liver": r"liver|hepat",
    "asthma": r"asthma|copd|respiratory disease",
    "ulcer": r"ulcer|gastritis|hyperacid",
    "thyroid": r"thyroid",
    "lactation": r"lactat|breast.?feed|nursing mothers?",
    "children": r"child|infant|toddler|pediatric|paediatric|baby|babies",
}
_CUE = re.compile(r"\b(avoid|contraindicated|not recommended|not advised|not suitable|should not|must not|do not use|"
                  r"unsafe|prohibited|caution)\b[^.;\n]{0,80}", re.I)


@dataclass
class Query:
    symptoms: list[str]
    text: str
    problem_hint: str | None = None
    lang: str = "en"
    conditions: set[str] = field(default_factory=set)  # normalised condition keys (see CONDITION_TERMS)


@dataclass
class RetrievalResult:
    mode: str
    items: list[dict]
    groups: list[dict]
    dropped: list[dict]
    n_candidates: int
    no_match: bool
    thresholds: dict

    @property
    def ids(self) -> list[int]:
        return [i["record_id"] for i in self.items]


def profile_condition_keys(chronic_text: str = "", age_years: float | None = None, pregnant: bool = False) -> set[str]:
    keys = set()
    t = (chronic_text or "").lower()
    for k, pat in CONDITION_TERMS.items():
        if re.search(pat, t):
            keys.add(k)
    if pregnant:
        keys.add("pregnancy")
    if age_years is not None and age_years < 12:
        keys.add("children")
    return keys


def explicit_precautions(remedy_text: str) -> list[str]:
    """Precaution statements that are explicitly present in the record's own text
    and mention a recognised condition group. Diet advice like 'avoid oily food'
    does not match because no condition group is named."""
    found = []
    for m in _CUE.finditer(remedy_text or ""):
        seg = m.group(0)
        for key, pat in CONDITION_TERMS.items():
            if re.search(pat, seg, re.I):
                found.append(key)
    return sorted(set(found))


class Retriever:
    def __init__(self, ds, store, embedder, cfg):
        self.ds, self.store, self.embedder, self.cfg = ds, store, embedder, cfg
        self.weights = cfg.get("RANK_WEIGHTS")
        base = DEFAULT_THRESHOLDS.get(embedder.backend, DEFAULT_THRESHOLDS["sentence-transformers"])
        self.th_sym = cfg.get("RETRIEVAL_MIN_SYMPTOM_SIM") or base["symptom"]
        self.th_full = cfg.get("RETRIEVAL_MIN_FULL_SIM") or base["full"]
        self.n_cand = cfg.get("RETRIEVAL_CANDIDATES", 150)
        self._pos_by_id = {rid: p for p, rid in enumerate(store.ids)}
        self._gkeys = ds.df["problem_key"].tolist()
        self._records = ds.df

    # --------------------------------------------------------------- helpers
    def _candidates(self, v_sym, v_full):
        pos: set[int] = set()
        if len(v_sym):
            _, p = self.store.search("symptom", v_sym, self.n_cand)
            pos.update(int(x) for x in p.ravel())
        for view in ("full", "problem", "symptom"):
            _, p = self.store.search(view, v_full, self.n_cand)
            pos.update(int(x) for x in p.ravel())
        return sorted(pos)

    def _query_vectors(self, q: Query):
        syms = [s for s in q.symptoms if s.strip()] or []
        texts = syms + [q.text[:400] or " ".join(syms)]
        if q.problem_hint:
            texts.append(q.problem_hint)
        vecs = self.embedder.encode(texts, kind="query")
        n = len(syms)
        v_sym = vecs[:n] if n else vecs[n:n + 1] * 0  # (0,d) if no symptoms
        if not n:
            v_sym = vecs[0:0]
        v_full = vecs[n:n + 1]
        v_hint = vecs[n + 1:n + 2] if q.problem_hint else None
        # when no symptoms were extracted use the raw text as the single symptom query
        if not n:
            v_sym = v_full
        return v_sym, v_full, v_hint

    # ---------------------------------------------------------------- search
    def search(self, q: Query, mode: str = "proposed", k: int = 10) -> RetrievalResult:
        v_sym, v_full, v_hint = self._query_vectors(q)
        cand = self._candidates(v_sym, v_full)
        M = self.store.mats
        sym_mat = M["symptom"][cand] @ v_sym.T                       # (nc, ns)
        sym_best = sym_mat.max(axis=1)
        full_sim = (M["full"][cand] @ v_full.T).ravel()
        prob_q = v_hint if v_hint is not None else v_full
        prob_sim = (M["problem"][cand] @ prob_q.T).ravel()
        th = {"symptom": float(self.th_sym), "full": float(self.th_full), "mode": mode}

        if mode == "problem_only":
            return self._problem_only(q, cand, prob_sim, th, k)

        w = self.weights
        if mode == "symptom_rag":
            score = 0.6 * sym_best + 0.3 * full_sim + 0.1 * prob_sim
            order = np.argsort(-score)[:k]
            items = [self._item(cand[i], score[i], sym_best[i], full_sim[i], prob_sim[i],
                                self._matched(q, sym_mat[i])) for i in order]
            return RetrievalResult(mode, items, [], [], len(cand), not items, th)

        # ---- proposed ------------------------------------------------------
        # problem-group symptom coverage: how well do ALL symptoms documented for the
        # group (not just this one record) cover what the user reported?
        cov_cache: dict[str, float] = {}

        def coverage(gkey: str) -> float:
            if gkey not in cov_cache:
                gpos = self.ds.positions_for_group(gkey)
                gm = M["symptom"][gpos] @ v_sym.T            # (|g|, ns)
                cov_cache[gkey] = float(gm.max(axis=0).mean())
            return cov_cache[gkey]

        score = np.zeros(len(cand))
        for i, pos in enumerate(cand):
            score[i] = (w["symptom"] * sym_best[i] + w["coverage"] * coverage(self._gkeys[pos])
                        + w["full"] * full_sim[i] + w["problem"] * prob_sim[i])

        kept, dropped = [], []
        seen_remedy: dict[tuple, int] = {}
        for i in np.argsort(-score):
            pos = cand[i]
            rec = self._records.iloc[pos]
            rid = int(rec["record_id"])
            if sym_best[i] < th["symptom"] and full_sim[i] < th["full"]:
                dropped.append({"record_id": rid, "reason": "below_relevance_threshold"})
                continue
            if self.cfg.get("EXCLUDE_DATASET_HIGH", True) and rec["risk"] == "High":
                dropped.append({"record_id": rid, "reason": "dataset_risk_high"})
                continue
            if rec["risk_status"] in ("conflict", "invalid"):
                dropped.append({"record_id": rid, "reason": f"risk_{rec['risk_status']}"})
                continue
            prec = explicit_precautions(rec["remedy_en"])
            hit = sorted(set(prec) & q.conditions)
            if hit:
                dropped.append({"record_id": rid, "reason": "precaution_matches_profile:" + ",".join(hit)})
                continue
            dkey = (rec["problem_key"], re.sub(r"\W+", " ", rec["remedy_en"].lower()).strip())
            if dkey in seen_remedy:
                dropped.append({"record_id": rid, "reason": f"duplicate_of:{seen_remedy[dkey]}"})
                continue
            seen_remedy[dkey] = rid
            item = self._item(pos, score[i], sym_best[i], full_sim[i], prob_sim[i], self._matched(q, sym_mat[i]))
            item["group_coverage"] = round(coverage(rec["problem_key"]), 4)
            item["precautions_in_text"] = prec
            kept.append(item)

        groups = self._diversify(kept)
        flat = [it for g in groups for it in g["items"]][:k]
        return RetrievalResult(mode, flat, groups, dropped, len(cand), not flat, th)

    # --------------------------------------------------------------- internals
    def _matched(self, q: Query, row) -> list[str]:
        if not q.symptoms:
            return []
        return [s for s, v in zip(q.symptoms, row) if v >= self.th_sym]

    def _item(self, pos, score, sym, full, prob, matched):
        rec = self._records.iloc[pos]
        return {"record_id": int(rec["record_id"]), "pos": int(pos), "score": round(float(score), 4),
                "symptom_sim": round(float(sym), 4), "full_sim": round(float(full), 4),
                "problem_sim": round(float(prob), 4), "matched_symptoms": matched,
                "problem_key": rec["problem_key"]}

    def _diversify(self, kept: list[dict]) -> list[dict]:
        """Group by problem. Keep several remedies per problem when they are comparably
        relevant (instead of picking one arbitrarily) and cap the number of problems."""
        by_group: dict[str, list[dict]] = {}
        for it in kept:  # `kept` is already score-descending
            by_group.setdefault(it["problem_key"], []).append(it)
        ranked = sorted(by_group.items(), key=lambda kv: -kv[1][0]["score"])
        out = []
        for gkey, items in ranked[: self.cfg.get("MAX_PROBLEM_GROUPS", 3)]:
            top = items[0]["score"]
            sel = [i for i in items if top - i["score"] <= self.cfg.get("GROUP_SCORE_DELTA", 0.06)]
            sel = sel[: self.cfg.get("MAX_REMEDIES_PER_GROUP", 3)]
            out.append({"problem_key": gkey, "best_score": top, "items": sel})
        return out

    def _problem_only(self, q, cand, prob_sim, th, k):
        # best-matching problem names; records returned in DATASET order (arbitrary w.r.t. symptoms)
        best: dict[str, float] = {}
        for i, pos in enumerate(cand):
            g = self._gkeys[pos]
            best[g] = max(best.get(g, -1), float(prob_sim[i]))
        items = []
        for g, s in sorted(best.items(), key=lambda kv: -kv[1]):
            for pos in self.ds.positions_for_group(g):
                items.append(self._item(pos, s, 0.0, 0.0, s, []))
            if len(items) >= k:
                break
        items = items[:k]
        return RetrievalResult("problem_only", items, [], [], len(cand), not items, th)

    # -------------------------------------------------------------- utilities
    def calibration_report(self, n_samples: int = 400, seed: int = 7) -> dict:
        """Similarity distributions to help choose thresholds (self-match vs random)."""
        rng = np.random.default_rng(seed)
        n = len(self.store.ids)
        idx = rng.choice(n, size=min(n_samples, n), replace=False)
        texts = [self.store_text(i) for i in idx]
        q = self.embedder.encode(texts, kind="query")
        sym = self.store.mats["symptom"]
        self_sim = np.einsum("ij,ij->i", q, sym[idx])
        rand = sym[rng.integers(0, n, size=len(idx))]
        rand_sim = np.einsum("ij,ij->i", q, rand)
        pct = [5, 25, 50, 75, 95]
        return {"backend": self.embedder.backend, "model": self.embedder.name,
                "self_match_percentiles": {p: round(float(np.percentile(self_sim, p)), 4) for p in pct},
                "random_pair_percentiles": {p: round(float(np.percentile(rand_sim, p)), 4) for p in pct},
                "current_thresholds": {"symptom": float(self.th_sym), "full": float(self.th_full)},
                "note": "Choose a symptom threshold between the random-pair 95th percentile and the "
                        "self-match 25th percentile, then validate it on the expert-verified dev set."}

    def store_text(self, pos: int) -> str:
        r = self._records.iloc[int(pos)]
        return r["symptom_en"] or r["symptom_ta"]
