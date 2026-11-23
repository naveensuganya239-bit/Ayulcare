"""Gemini wrapper (server-side only).

Gemini is used for: structured symptom extraction, optional clarifying question,
grounded explanation of retrieved records, and (checked) translation of remedy text.
Gemini is NEVER used to decide emergency risk, and never sees names/contacts.

Every call degrades gracefully: if no API key or the call fails, callers fall back to
deterministic templates so the app remains functional (and testable offline).
"""
from __future__ import annotations

import json
import logging
import re

log = logging.getLogger(__name__)

LANG_NAME = {"en": "English", "ta": "Tamil", "te": "Telugu", "hi": "Hindi"}

SYSTEM_GROUNDED = """You are the explanation layer of an informational Ayurvedic health-information research prototype.
HARD RULES:
1. Use ONLY the RECORDS provided. Never add remedies, ingredients, quantities, dosages, durations, contraindications or sources that are not in the records.
2. Never diagnose. Never claim a remedy is effective, proven, safe or cures anything. Say records "describe" or "mention".
3. Refer to records only by their ids like [R1]. Never invent ids, authors or books.
4. Respect the RISK_LEVEL: for medium risk, encourage seeing a doctor and keep it brief; never contradict the safety note.
5. Do not repeat the safety note verbatim; add at most one sentence on when to seek medical care.
6. Write in {language}. Keep medical/Ayurvedic terms and numbers exactly as in the records.
7. Output ONLY JSON: {{"summary": str, "why_matched": [{{"id": "R1", "reason": str}}], "care_note": str}}
   - summary: 2-3 sentences, plain language, describing what the records say in relation to the reported symptoms.
   - why_matched: one short sentence per record id explaining which reported symptom it relates to (use only the 'matched_symptoms' given).
   - care_note: one sentence on when to seek medical care."""

SYSTEM_EXTRACT = """You extract structured symptom information from a patient's message (any of English, Tamil, Telugu, Hindi, or mixed).
Do NOT diagnose and do NOT give advice. Output ONLY JSON with keys:
{"symptoms": [short English symptom terms], "negated_symptoms": [symptoms explicitly denied], "duration_days": number|null,
 "severity": "mild"|"moderate"|"severe"|null, "temperature_celsius": number|null, "worsening": boolean,
 "for_someone_else": boolean, "patient_age_years": number|null, "possible_problem_name": string|null}
Use only what the message states. Use null when unknown."""

SYSTEM_TRANSLATE = """Translate the given traditional-remedy text into {language}.
Keep every ingredient name, number, quantity, unit and warning EXACTLY as in the source (transliterate names if needed).
Do not add, remove or improve anything. Output ONLY the translation text."""

SYSTEM_QUESTION = """You help a symptom-intake assistant. Given reported symptoms, write ONE short, neutral follow-up question in {language}
that helps characterise the main symptom (e.g. dry vs productive cough, location of pain). Do not diagnose or advise.
Do not repeat anything in ALREADY_ASKED. Output ONLY the question text."""


class GeminiClient:
    def __init__(self, api_key: str, model: str, timeout: int = 30):
        self.api_key, self.model, self.timeout = api_key, model, timeout
        self._client = None

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def _get(self):
        if self._client is None:
            from google import genai  # lazy import
            self._client = genai.Client(api_key=self.api_key)
        return self._client

    def _generate(self, system: str, user: str, json_mode: bool, max_tokens: int = 900) -> str | None:
        if not self.enabled:
            return None
        try:
            from google.genai import types
            cfg = types.GenerateContentConfig(
                system_instruction=system, temperature=0.2, max_output_tokens=max_tokens,
                response_mime_type="application/json" if json_mode else "text/plain",
            )
            resp = self._get().models.generate_content(model=self.model, contents=user, config=cfg)
            return (resp.text or "").strip() or None
        except Exception as exc:  # network / quota / safety block
            log.warning("Gemini call failed: %s", type(exc).__name__)
            return None

    @staticmethod
    def _json(raw: str | None):
        if not raw:
            return None
        raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.M).strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            m = re.search(r"\{.*\}", raw, re.S)
            if m:
                try:
                    return json.loads(m.group(0))
                except json.JSONDecodeError:
                    return None
        return None

    # ------------------------------------------------------------------ API
    def extract(self, text: str, ctx_summary: str = "") -> dict | None:
        data = self._json(self._generate(SYSTEM_EXTRACT, f"KNOWN_SO_FAR: {ctx_summary}\nMESSAGE: {text}", True, 400))
        if not isinstance(data, dict):
            return None
        out = {
            "symptoms": [str(s).strip().lower()[:60] for s in data.get("symptoms", []) if isinstance(s, str) and s.strip()][:10],
            "negated": [str(s).strip().lower()[:60] for s in data.get("negated_symptoms", []) if isinstance(s, str)][:10],
            "duration_days": data.get("duration_days") if isinstance(data.get("duration_days"), (int, float)) else None,
            "severity": data.get("severity") if data.get("severity") in ("mild", "moderate", "severe") else None,
            "fever_c": data.get("temperature_celsius") if isinstance(data.get("temperature_celsius"), (int, float)) and 34 <= data["temperature_celsius"] <= 43 else None,
            "worsening": bool(data.get("worsening")),
            "other_subject": bool(data.get("for_someone_else")),
            "patient_age_years": data.get("patient_age_years") if isinstance(data.get("patient_age_years"), (int, float)) and 0 <= data["patient_age_years"] <= 120 else None,
            "problem_hint": (data.get("possible_problem_name") or None),
        }
        return out

    def clarifying_question(self, symptoms: list[str], language: str, already_asked: list[str]) -> str | None:
        raw = self._generate(SYSTEM_QUESTION.format(language=LANG_NAME.get(language, "English")),
                             f"SYMPTOMS: {', '.join(symptoms)}\nALREADY_ASKED: {already_asked}", False, 120)
        if raw and len(raw) < 220 and "?" in raw or (raw and raw.endswith(("?", "？"))):
            return raw
        return None

    def explain(self, records: list[dict], risk_level: str, symptoms: list[str], language: str,
                safety_note: str, context: dict) -> dict | None:
        payload = {
            "RISK_LEVEL": risk_level, "SAFETY_NOTE": safety_note, "REPORTED_SYMPTOMS": symptoms,
            "USER_CONTEXT_(de-identified)": context,
            "RECORDS": [{"id": r["ref"], "problem": r["problem_en"], "symptom": r["symptom_en"],
                         "remedy": r["remedy_en"], "author": r["author"], "book": r["book"],
                         "matched_symptoms": r.get("matched_symptoms", [])} for r in records],
        }
        data = self._json(self._generate(SYSTEM_GROUNDED.format(language=LANG_NAME.get(language, "English")),
                                         json.dumps(payload, ensure_ascii=False), True, 900))
        return data if isinstance(data, dict) else None

    def translate_remedy(self, text: str, language: str) -> str | None:
        return self._generate(SYSTEM_TRANSLATE.format(language=LANG_NAME.get(language, "English")), text, False, 400)

    def summarise_external(self, results: list[dict], language: str, symptoms: list[str]) -> str | None:
        system = ("Summarise the provided SNIPPETS from trusted health websites in " + LANG_NAME.get(language, "English") +
                  ". Use ONLY the snippets. NO dosages, NO prescriptions, NO treatment instructions, NO diagnosis. "
                  "2-3 sentences of general education. Mention that this is external information. Output plain text only.")
        return self._generate(system, json.dumps({"symptoms": symptoms, "SNIPPETS": [
            {"source": r["source"], "title": r["title"], "snippet": r["snippet"]} for r in results]}, ensure_ascii=False), False, 400)


# ------------------------------------------------------------ output guards
_NUM = re.compile(r"\d+(?:[.,]\d+)?")
_ALLOWED_NUMS = {"108", "112", "14416", "1", "2", "3", "7", "14", "24", "48", "72"}
_INDIC_DIGITS = str.maketrans("௦௧௨௩௪௫௬௭௮௯౦౧౨౩౪౫౬౭౮౯०१२३४५६७८९", "01234567890123456789" + "0123456789")


def numbers_in(text: str) -> list[str]:
    t = (text or "").translate(_INDIC_DIGITS)
    return [n.replace(",", ".") for n in _NUM.findall(t)]


def numbers_preserved(source: str, translation: str) -> bool:
    return sorted(numbers_in(source)) == sorted(numbers_in(translation))


def validate_explanation(data: dict | None, refs: set[str], records_text: str, user_text: str) -> dict | None:
    """Reject LLM output that cites unknown records or introduces numbers (e.g. doses)
    that appear neither in the retrieved records nor in the user's own message."""
    if not data or not isinstance(data.get("summary"), str):
        return None
    allowed = set(numbers_in(records_text)) | set(numbers_in(user_text)) | _ALLOWED_NUMS
    blob = " ".join([data.get("summary", ""), data.get("care_note", "") or ""] +
                    [str(w.get("reason", "")) for w in data.get("why_matched", []) if isinstance(w, dict)])
    if any(n not in allowed for n in numbers_in(blob)):
        return None
    cited = set(re.findall(r"\[?(R\d+)\]?", blob))
    if cited - refs:
        return None
    for w in data.get("why_matched", []) or []:
        if not isinstance(w, dict) or w.get("id") not in refs:
            return None
    return data
