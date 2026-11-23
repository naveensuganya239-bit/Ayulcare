"""Read-only data access + validation layer for the Ayurvedic CSV.

Guarantees
----------
* The CSV is opened read-only and never written, cleaned, de-duplicated or re-saved.
* Every original value is preserved verbatim in the in-memory records
  (only *matching* helpers normalise whitespace/case, never the stored value).
* Header inconsistencies (e.g. "Risk level" vs "Risk Level", blank headers,
  "Problem faced in English" vs "Problem in English") are resolved
  programmatically with a transparent per-record fallback rule.
* Conflicting risk labels are FLAGGED (risk=None, status="conflict"), never
  silently resolved.
* Integrity of the source file is verified against a SHA-256 baseline.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

VALID_RISK = {"low": "Low", "medium": "Medium", "high": "High"}

# canonical field -> normalised header names that feed it (priority order)
CANONICAL_SOURCES: dict[str, list[str]] = {
    "sno": ["sno"],
    "symptom_en": ["symptomsinenglish"],
    "symptom_ta": ["symptomsintamil"],
    "problem_en": ["problemfacedinenglish", "probleminenglish"],
    "problem_ta": ["problemfacedintamil", "probleminTamil".lower()],
    "remedy_en": ["remedyforprobleminenglish"],
    "remedy_ta": ["remedyforproblemintamil"],
    "author": ["author"],
    "book": ["book"],
}
RISK_HEADER = "risklevel"


def _norm_header(h: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (h or "").lower())


def norm_text(s: str) -> str:
    """Matching-only normalisation. Never used to alter stored values."""
    return re.sub(r"\s+", " ", (s or "").strip()).lower()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class DatasetStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.sha256 = sha256_file(self.path)
        self.column_map: dict[str, list[str]] = {}
        self.risk_columns: list[tuple[int, str]] = []
        self.quality: dict = {}
        self.df: pd.DataFrame = pd.DataFrame()
        self._by_id: dict[int, int] = {}
        self.groups: dict[str, list[int]] = {}
        self._load()

    # ------------------------------------------------------------------ load
    def _read_raw(self) -> tuple[list[str], list[list[str]]]:
        with open(self.path, "r", encoding="utf-8-sig", newline="") as f:  # read-only
            rows = list(csv.reader(f))
        header, body = rows[0], rows[1:]
        width = max(len(header), *(len(r) for r in body)) if body else len(header)
        header = header + [""] * (width - len(header))
        body = [r + [""] * (width - len(r)) for r in body]
        return header, body

    def _load(self) -> None:
        header, body = self._read_raw()
        norm = [_norm_header(h) for h in header]

        # canonical (non-risk) column positions
        positions: dict[str, list[int]] = {}
        for canon, names in CANONICAL_SOURCES.items():
            positions[canon] = [i for i, n in enumerate(norm) if n in names]

        # risk columns: any header normalising to "risklevel" (case-insensitive)
        # + blank-header columns whose non-empty values are all valid risk labels
        risk_cols = [i for i, n in enumerate(norm) if n == RISK_HEADER]
        for i, n in enumerate(norm):
            if n == "" and i not in risk_cols:
                vals = [r[i].strip() for r in body if r[i].strip()]
                if vals and all(v.lower() in VALID_RISK for v in vals):
                    risk_cols.append(i)
        risk_cols.sort()
        self.risk_columns = [(i, header[i] if header[i].strip() else f"(unnamed column #{i + 1})") for i in risk_cols]
        self.column_map = {k: [header[i] for i in v] for k, v in positions.items()}
        self.column_map["risk"] = [name for _, name in self.risk_columns]

        records = []
        stats = Counter()
        for row_idx, row in enumerate(body):
            rec: dict = {"row_index": row_idx}
            flags: list[str] = []
            for canon, idxs in positions.items():
                vals = [row[i] for i in idxs if row[i].strip()]
                rec[canon] = vals[0] if vals else ""
                if len({norm_text(v) for v in vals}) > 1:
                    flags.append(f"conflict:{canon}")
            # risk resolution ------------------------------------------------
            seen = [(name, row[i].strip()) for i, name in self.risk_columns if row[i].strip()]
            normalised = [(n, VALID_RISK.get(v.lower())) for n, v in seen]
            if not seen:
                rec.update(risk=None, risk_status="missing", risk_source=None, risk_raw=None)
            elif any(v is None for _, v in normalised):
                rec.update(risk=None, risk_status="invalid", risk_source=seen[0][0], risk_raw=seen[0][1])
                flags.append("risk:invalid")
            else:
                distinct = {v for _, v in normalised}
                if len(distinct) > 1:
                    rec.update(risk=None, risk_status="conflict", risk_source=None, risk_raw="/".join(v for _, v in seen))
                    flags.append("risk:conflict")
                else:
                    first_name, first_raw = seen[0]
                    primary_name = self.risk_columns[0][1]
                    status = "ok" if first_name == primary_name else "fallback"
                    rec.update(risk=normalised[0][1], risk_status=status, risk_source=first_name, risk_raw=first_raw)
                    if first_raw != normalised[0][1]:
                        stats["risk_case_normalised"] += 1
            rec["flags"] = flags
            records.append(rec)

        df = pd.DataFrame(records)
        # record id = SNo if it is a unique integer, else row number (flagged)
        sno_num = pd.to_numeric(df["sno"], errors="coerce")
        if sno_num.notna().all() and sno_num.is_unique:
            df["record_id"] = sno_num.astype(int)
        else:
            df["record_id"] = df["row_index"] + 1
            stats["sno_not_unique_used_row_index"] = 1
        self.df = df.set_index("record_id", drop=False)
        self._by_id = {rid: pos for pos, rid in enumerate(df["record_id"].tolist())}

        self.groups = defaultdict(list)
        for pos, p in enumerate(df["problem_en"].tolist()):
            self.groups[norm_text(p)].append(pos)
        self.groups = dict(self.groups)
        self.df["problem_key"] = [norm_text(p) for p in df["problem_en"]]
        self._stats = stats
        self.quality = self._quality_report(header, body)

    # ---------------------------------------------------------------- access
    def __len__(self) -> int:
        return len(self.df)

    def get(self, rid: int) -> dict | None:
        pos = self._by_id.get(int(rid))
        return None if pos is None else self.df.iloc[pos].to_dict()

    def positions_for_group(self, problem_key: str) -> list[int]:
        return self.groups.get(problem_key, [])

    def record_ids(self) -> list[int]:
        return self.df["record_id"].tolist()

    @staticmethod
    def public(rec: dict) -> dict:
        """API-safe view of a record (verbatim originals + provenance)."""
        return {
            "record_id": int(rec["record_id"]),
            "symptom_en": rec["symptom_en"], "symptom_ta": rec["symptom_ta"],
            "problem_en": rec["problem_en"], "problem_ta": rec["problem_ta"],
            "remedy_en": rec["remedy_en"], "remedy_ta": rec["remedy_ta"],
            "author": rec["author"], "book": rec["book"],
            "dataset_risk": rec["risk"], "risk_status": rec["risk_status"],
        }

    # ------------------------------------------------------------- integrity
    def verify_integrity(self, baseline_file: Path | None = None) -> dict:
        baseline_file = baseline_file or self.path.parent / "SHA256SUMS"
        current = sha256_file(self.path)
        expected = None
        if baseline_file.exists():
            for line in baseline_file.read_text().splitlines():
                parts = line.split()
                if len(parts) >= 2 and parts[1].lstrip("*") == self.path.name:
                    expected = parts[0]
        return {"file": self.path.name, "sha256": current, "baseline": expected,
                "intact": (expected is None) or (expected == current),
                "baseline_present": expected is not None}

    # --------------------------------------------------------------- quality
    def _quality_report(self, header: list[str], body: list[list[str]]) -> dict:
        df = self.df
        empty = {c: int((df[c].str.strip() == "").sum()) for c in
                 ["symptom_en", "symptom_ta", "problem_en", "problem_ta", "remedy_en", "remedy_ta", "author", "book"]}
        raw_risk_values = Counter()
        for i, _ in self.risk_columns:
            for r in body:
                if r[i].strip():
                    raw_risk_values[r[i].strip()] += 1
        multi = Counter(len(v) for v in self.groups.values())
        return {
            "source_file": self.path.name,
            "sha256": self.sha256,
            "n_records": int(len(df)),
            "n_header_columns": len(header),
            "header_columns_raw": header,
            "column_map": self.column_map,
            "risk_columns_used_in_priority_order": [n for _, n in self.risk_columns],
            "empty_values_per_field": empty,
            "risk_status_counts": dict(Counter(df["risk_status"])),
            "risk_final_distribution": dict(Counter(df["risk"].fillna("UNAVAILABLE"))),
            "risk_raw_value_variants": dict(raw_risk_values),
            "risk_case_normalised_in_memory": int(self._stats.get("risk_case_normalised", 0)),
            "records_flagged": int(sum(1 for f in df["flags"] if f)),
            "unique_problems": len(self.groups),
            "records_per_problem_histogram_top": dict(multi.most_common(12)),
            "unique_symptoms_en": int(df["symptom_en"].map(norm_text).nunique()),
            "unique_books": int(df["book"].nunique()),
            "unique_authors": int(df["author"].nunique()),
            "notes": [
                "The CSV is never modified. Case variants of risk labels are normalised only in memory.",
                "Where the primary risk column is empty, the next risk column is used (status=fallback).",
                "Conflicting risk labels yield risk=None and status=conflict (flagged, not resolved).",
            ],
        }

    def write_quality_report(self, out_dir: Path) -> Path:
        out_dir.mkdir(parents=True, exist_ok=True)
        p = out_dir / "data_quality.json"
        p.write_text(json.dumps(self.quality, indent=2, ensure_ascii=False), encoding="utf-8")
        return p
