"""Reproducible retrieval evaluation: Baseline 1 vs Baseline 2 vs Proposed."""
from __future__ import annotations

import csv
import json
import time
from pathlib import Path

from ..services.retrieval import Query
from ..services.risk import RULESET_VERSION
from ..services.symptoms import extract_rule_based
from .metrics import hit_at_k, precision_at_k, recall_at_k, reciprocal_rank, summarise
from .testset import read_testset

MODES = {"problem_only": "Baseline 1: problem-name-only retrieval",
         "symptom_rag": "Baseline 2: symptom-aware RAG retrieval",
         "proposed": "Proposed: symptom-aware retrieval + relevance & safety filtering"}


def run_retrieval_eval(svc, cfg, testset_path: str, ks: list[int], name: str | None = None, include_unverified: bool = False) -> dict:
    base = Path(cfg["BASE_DIR"])
    tp = Path(testset_path) if Path(testset_path).is_absolute() else base / testset_path
    if not tp.exists():
        raise FileNotFoundError(f"Test set not found: {tp}. Create it from data/eval/retrieval_testset_TEMPLATE.csv with expert verification.")
    cases = read_testset(tp, include_unverified)
    if not cases:
        raise RuntimeError("No verified test cases found (rows need relevant_snos and verified=yes).")
    kmax = max(ks)
    results: dict[str, dict] = {}
    per_query_rows = []
    for mode in MODES:
        pq = []
        for c in cases:
            syms = c["symptoms"] or extract_rule_based(c["text"]).symptoms
            res = svc.retriever.search(Query(symptoms=syms, text=c["text"], lang=c["language"]), mode, k=kmax)
            ranked = res.ids
            row = {"query_id": c["query_id"], "language": c["language"], "rr": reciprocal_rank(ranked, c["relevant"]),
                   "n_returned": len(ranked), "no_match": res.no_match}
            for k in ks:
                row[f"precision@{k}"] = precision_at_k(ranked, c["relevant"], k)
                row[f"recall@{k}"] = recall_at_k(ranked, c["relevant"], k)
                row[f"hit@{k}"] = hit_at_k(ranked, c["relevant"], k)
            pq.append(row)
            per_query_rows.append({"mode": mode, **row, "top_ids": ranked[:kmax]})
        summ = summarise(pq, ks)
        summ["no_match_rate"] = round(sum(1 for r in pq if r["no_match"]) / len(pq), 4)
        langs = sorted({r["language"] for r in pq})
        summ["by_language"] = {lg: summarise([r for r in pq if r["language"] == lg], ks) for lg in langs}
        results[mode] = {"label": MODES[mode], "summary": summ}

    meta = {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "dataset_sha256": svc.ds.sha256, "n_records": len(svc.ds),
            "embedding_backend": svc.embedder.backend, "embedding_model": svc.embedder.name,
            "thresholds": {"symptom": svc.retriever.th_sym, "full": svc.retriever.th_full}, "rank_weights": cfg["RANK_WEIGHTS"],
            "testset": tp.name, "n_cases": len(cases), "n_verified": sum(1 for c in cases if c["verified"]),
            "ks": ks, "risk_ruleset": RULESET_VERSION,
            "warning": ("NOT FOR PUBLICATION: embedding backend is the offline 'hash' fallback." if svc.embedder.backend == "hash" else None) or
                       ("Includes UNVERIFIED cases." if any(not c["verified"] for c in cases) else None)}
    stamp = time.strftime("%Y%m%d_%H%M%S")
    label = f"eval_retrieval_{name or stamp}"
    out_dir = Path(cfg["REPORT_DIR"])
    out_dir.mkdir(parents=True, exist_ok=True)
    report = {"meta": meta, "results": results}
    jp = out_dir / f"{label}.json"
    jp.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    with open(out_dir / f"{label}_per_query.csv", "w", newline="", encoding="utf-8") as f:
        cols = ["mode", "query_id", "language", "rr", "n_returned", "no_match"] + [f"{m}@{k}" for k in ks for m in ("precision", "recall", "hit")] + ["top_ids"]
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in per_query_rows:
            r = dict(r)
            r["top_ids"] = ";".join(map(str, r["top_ids"]))
            w.writerow(r)
    _write_markdown(out_dir / f"{label}.md", report, ks)
    return {"summary": {m: {k: v for k, v in r["summary"].items() if k in ("n_queries", "mrr", "precision@5", "recall@5", "no_match_rate")}
                        for m, r in results.items()}, "path": str(jp)}


def _write_markdown(path: Path, report: dict, ks: list[int]) -> None:
    m = report["meta"]
    lines = [f"# Retrieval evaluation ({m['created']})", "",
             f"- Dataset SHA-256: `{m['dataset_sha256']}` ({m['n_records']} records)",
             f"- Embedding: {m['embedding_backend']} / {m['embedding_model']}",
             f"- Test cases: {m['n_cases']} (verified: {m['n_verified']}) from `{m['testset']}`"]
    if m.get("warning"):
        lines += ["", f"> **{m['warning']}**"]
    head = "| System | MRR | " + " | ".join(f"P@{k} | R@{k}" for k in ks) + " | No-match |"
    lines += ["", head, "|" + "---|" * (3 + 2 * len(ks))]
    for mode, r in report["results"].items():
        s = r["summary"]
        lines.append(f"| {r['label']} | {s['mrr']} | " + " | ".join(f"{s[f'precision@{k}']} | {s[f'recall@{k}']}" for k in ks) + f" | {s['no_match_rate']} |")
    lines += ["", "Similarity scores are ranking signals, not medical confidence. Metrics measure agreement with expert relevance judgments, not clinical effectiveness."]
    path.write_text("\n".join(lines), encoding="utf-8")
