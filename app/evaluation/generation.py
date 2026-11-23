"""Automatic proxies for generation quality (complement, never replace, expert rating).

unsupported_statement_check: flags numbers and record references in an assessment payload's
narrative that are not supported by the retrieved records.
"""
from __future__ import annotations

from ..services.gemini import numbers_in


def unsupported_statement_check(payload: dict, user_text: str = "") -> dict:
    recs = payload.get("remedies") or []
    support = " ".join(f"{r['remedy_en']} {r['problem_en']} {r['symptom_en']}" for r in recs)
    allowed = set(numbers_in(support)) | set(numbers_in(user_text)) | {"108", "112", "14416", "1", "2", "3", "7", "14", "24", "48", "72"}
    narrative = " ".join(filter(None, [payload.get("narrative"), payload.get("care_note")]))
    bad = [n for n in numbers_in(narrative) if n not in allowed]
    ungrounded = bool(narrative) and not recs
    return {"unsupported_numbers": bad, "narrative_without_records": ungrounded, "ok": not bad and not ungrounded}
