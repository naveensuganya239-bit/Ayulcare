"""Test-set tooling. The gold standard MUST be created/verified by qualified experts.

Template columns
  query_id, language, query_text, symptoms_en, relevant_snos, reviewer, verified, notes
  * query_text : natural patient-style description (experts rewrite the draft)
  * symptoms_en: optional ';'-separated English symptom terms (blank -> automatic extraction)
  * relevant_snos: ';'-separated SNo values the expert judges appropriate to retrieve
  * verified   : 'yes' only after expert review. Unverified rows are excluded from reported results.
"""
from __future__ import annotations

import csv
from pathlib import Path

import numpy as np

COLUMNS = ["query_id", "language", "query_text", "symptoms_en", "relevant_snos", "reviewer", "verified", "notes"]


def write_template(ds, out_dir: Path, n: int = 150, seed: int = 11) -> Path:
    """Stratified (by problem) DRAFT sample. The draft query is taken from the record's own
    symptom text purely as a starting point; relevant_snos is intentionally left EMPTY.
    Using self-generated queries as ground truth would be circular, so verified=no."""
    rng = np.random.default_rng(seed)
    keys = sorted(ds.groups)
    chosen = rng.choice(len(keys), size=min(n, len(keys)), replace=False)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "retrieval_testset_TEMPLATE.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(COLUMNS)
        for i, ci in enumerate(chosen, 1):
            pos = ds.groups[keys[ci]][0]
            rec = ds.df.iloc[pos]
            w.writerow([f"Q{i:03d}", "en", f"DRAFT: {rec['symptom_en']}", rec["symptom_en"], "", "", "no",
                        f"seed problem group: {rec['problem_en']} ({len(ds.groups[keys[ci]])} records)"])
    return path


def read_testset(path: Path, include_unverified: bool = False) -> list[dict]:
    rows = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            if not r.get("query_text") or not r.get("relevant_snos", "").strip():
                continue
            if r.get("verified", "").strip().lower() != "yes" and not include_unverified:
                continue
            rows.append({"query_id": r["query_id"], "language": (r.get("language") or "en").strip(),
                         "text": r["query_text"].strip(),
                         "symptoms": [s.strip() for s in (r.get("symptoms_en") or "").split(";") if s.strip()],
                         "relevant": {int(x) for x in r["relevant_snos"].replace(",", ";").split(";") if x.strip().isdigit()},
                         "verified": r.get("verified", "").strip().lower() == "yes"})
    return rows


def write_rating_sheet(payloads: list[dict], path: Path) -> Path:
    """Manual rating sheet for generation quality (faithfulness / relevance / completeness, 1-5)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["case_id", "query", "retrieved_records", "system_answer", "faithfulness_1to5", "relevance_1to5",
                    "completeness_1to5", "unsupported_statements", "rater", "notes"])
        for p in payloads:
            w.writerow([p.get("case_id"), p.get("query"), p.get("records"), p.get("answer"), "", "", "", "", "", ""])
    return path
