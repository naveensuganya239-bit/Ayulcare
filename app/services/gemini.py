"""Gemini wrapper (server-side only).

Gemini is used for: structured symptom extraction, optional clarifying question,
grounded explanation of retrieved records, and (checked) translation of remedy text.
Gemini is NEVER used to decide emergency risk, and never sees names/contacts.

Every call degrades gracefully: if no API key or the call fails, callers fall back to
deterministic templates so the app remains functional (and testable offline).

Supported free-tier models (Google AI Studio):
  gemini-1.5-flash   (recommended — fast, free, 1M context)
  gemini-1.5-pro     (slower, free quota limited)
  gemini-2.0-flash   (free tier available)
"""
from __future__ import annotations

import json
import logging
import re

log = logging.getLogger(__name__)

LANG_NAME = {"en": "English", "ta": "Tamil", "te": "Telugu", "hi": "Hindi"}

# ---------------------------------------------------------------------------
# SYSTEM_GROUNDED — the most critical prompt: Gemini explains retrieved records
# ---------------------------------------------------------------------------
SYSTEM_GROUNDED = """\
You are the Ayurvedic remedy explanation layer in a health-information research prototype.

HARD RULES (never break any of these):
1. Use ONLY the RECORDS provided. Do NOT add, infer, or suggest any remedy, ingredient,
   quantity, dosage, duration, contraindication or source that is not explicitly in the records.
2. Never diagnose. Never claim that a remedy is effective, proven, or safe, or that it
   cures / treats / heals anything. Use phrases like "the records describe", "the book mentions".
3. Cite records ONLY by their given ids (R1, R2, …). Never invent ids, author names, or book titles.
4. Respect RISK_LEVEL:
   - low  → present remedies concisely; include a brief care note.
   - medium → one sentence of book info only; strongly encourage seeing a doctor.
5. Never repeat the SAFETY_NOTE word-for-word; instead add ONE sentence on when to seek care.
6. Reply in {language}. Preserve ALL Ayurvedic / medical terms and numbers EXACTLY as in the records.
7. Be specific: for each remedy, mention the exact preparation or action stated in the record
   (e.g. "Take X powder with warm water twice daily" not just "use X").
8. Keep the summary to 3–5 sentences maximum. Do not pad with generic disclaimers.
9. Output ONLY valid JSON — no markdown, no extra text:
   {{
     "summary": "<3-5 sentence overview of what the records say about the reported symptoms>",
     "why_matched": [
       {{"id": "R1", "reason": "<one sentence: which symptom matched and how the record relates>"}}
     ],
     "care_note": "<one specific sentence on when / why to see a doctor for this case>"
   }}
"""

# ---------------------------------------------------------------------------
# SYSTEM_EXTRACT — symptom extraction with Ayurvedic term awareness
# ---------------------------------------------------------------------------
SYSTEM_EXTRACT = """\
You extract structured symptom data from a patient message. The message may be in English,
Tamil, Telugu, Hindi, or a mix. Recognise Ayurvedic problem names (e.g. "vata", "pitta",
"gulma", "aruchi", "hikka") as possible_problem_name hints.

Do NOT diagnose. Do NOT give advice. Output ONLY valid JSON with these exact keys:
{{
  "symptoms":            [<short English symptom terms, lowercase>],
  "negated_symptoms":    [<symptoms the patient explicitly says they do NOT have>],
  "duration_days":       <number or null>,
  "severity":            "mild" | "moderate" | "severe" | null,
  "temperature_celsius": <number 34-43 or null>,
  "worsening":           true | false,
  "for_someone_else":    true | false,
  "patient_age_years":   <number 0-120 or null>,
  "possible_problem_name": "<Ayurvedic or common disease name if mentioned, else null>"
}}
Use only information explicitly stated in the message. Use null for anything unknown.
"""

# ---------------------------------------------------------------------------
# SYSTEM_TRANSLATE — strict translation (numbers & ingredient names preserved)
# ---------------------------------------------------------------------------
SYSTEM_TRANSLATE = """\
Translate the following traditional Ayurvedic remedy text into {language}.
Rules:
- Keep every ingredient name, quantity, unit, number, and warning EXACTLY as in the source.
- Transliterate Sanskrit / Ayurvedic ingredient names rather than translating them.
- Do NOT add, omit, or reinterpret anything.
- Output ONLY the translated text. No commentary.
"""

# ---------------------------------------------------------------------------
# SYSTEM_QUESTION — targeted follow-up question generation
# ---------------------------------------------------------------------------
SYSTEM_QUESTION = """\
You assist a symptom-intake chatbot. Given a list of reported symptoms, generate EXACTLY ONE
short, neutral, clinically-useful follow-up question in {language} to better characterise the
main symptom (e.g. "Is the cough dry or producing mucus?", "Where exactly is the pain?",
"Does the rash have any blistering?").

Constraints:
- Do NOT diagnose, prescribe, or advise treatment.
- Do NOT repeat any question already in ALREADY_ASKED.
- Maximum 15 words in the question.
- Output ONLY the question text — no explanation, no preamble.
"""


class GeminiClient:
    def __init__(self, api_key: str, model: str, timeout: int = 30):
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self._client = None

    @property
    def enabled(self) -> bool:
        key = self.api_key or ""
        return bool(key) and key not in (
            "YOUR_GEMINI_API_KEY_HERE", "your-api-key-here", ""
        )

    def _get(self):
        if self._client is None:
            from google import genai  # lazy import
            self._client = genai.Client(api_key=self.api_key)
        return self._client

    def _generate(self, system: str, user: str, json_mode: bool,
                  max_tokens: int = 900) -> str | None:
        if not self.enabled:
            log.debug("Gemini disabled (no valid API key configured).")
            return None
        try:
            from google.genai import types
            cfg = types.GenerateContentConfig(
                system_instruction=system,
                temperature=0.1,          # lower = more precise / deterministic
                max_output_tokens=max_tokens,
                response_mime_type="application/json" if json_mode else "text/plain",
            )
            resp = self._get().models.generate_content(
                model=self.model,
                contents=user,
                config=cfg,
            )
            text = (resp.text or "").strip()
            return text or None
        except Exception as exc:
            exc_type = type(exc).__name__
            msg = str(exc)
            if "API_KEY_INVALID" in msg or "API key not valid" in msg:
                log.error(
                    "Gemini API key is INVALID. Get a free key at "
                    "https://aistudio.google.com/apikey and set GEMINI_API_KEY in .env"
                )
            elif "QUOTA_EXCEEDED" in msg or "quota" in msg.lower():
                log.warning("Gemini quota exceeded — using deterministic fallback.")
            elif "MODEL_NOT_FOUND" in msg or "not found" in msg.lower():
                log.error(
                    "Gemini model '%s' not found. "
                    "Set GEMINI_MODEL=gemini-1.5-flash in .env", self.model
                )
            elif "SAFETY" in msg:
                log.warning("Gemini safety filter — using fallback.")
            else:
                log.warning("Gemini call failed (%s): %s", exc_type, msg[:200])
            if exc_type in ("ConnectTimeout", "ReadTimeout", "ConnectionError"):
                self._client = None   # force reconnect next call
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
                    pass
        return None

    # ------------------------------------------------------------------ API
    def extract(self, text: str, ctx_summary: str = "") -> dict | None:
        prompt = (
            f"KNOWN_SYMPTOMS_SO_FAR: {ctx_summary}\n"
            f"NEW_PATIENT_MESSAGE: {text}"
        )
        data = self._json(self._generate(SYSTEM_EXTRACT, prompt, True, 500))
        if not isinstance(data, dict):
            return None
        return {
            "symptoms": [
                str(s).strip().lower()[:60]
                for s in data.get("symptoms", [])
                if isinstance(s, str) and s.strip()
            ][:10],
            "negated": [
                str(s).strip().lower()[:60]
                for s in data.get("negated_symptoms", [])
                if isinstance(s, str)
            ][:10],
            "duration_days": (
                data.get("duration_days")
                if isinstance(data.get("duration_days"), (int, float))
                else None
            ),
            "severity": (
                data.get("severity")
                if data.get("severity") in ("mild", "moderate", "severe")
                else None
            ),
            "fever_c": (
                data.get("temperature_celsius")
                if isinstance(data.get("temperature_celsius"), (int, float))
                and 34 <= data["temperature_celsius"] <= 43
                else None
            ),
            "worsening": bool(data.get("worsening")),
            "other_subject": bool(data.get("for_someone_else")),
            "patient_age_years": (
                data.get("patient_age_years")
                if isinstance(data.get("patient_age_years"), (int, float))
                and 0 <= data["patient_age_years"] <= 120
                else None
            ),
            "problem_hint": data.get("possible_problem_name") or None,
        }

    def clarifying_question(self, symptoms: list[str], language: str,
                             already_asked: list[str]) -> str | None:
        prompt = (
            f"REPORTED_SYMPTOMS: {', '.join(symptoms)}\n"
            f"ALREADY_ASKED: {json.dumps(already_asked)}"
        )
        raw = self._generate(
            SYSTEM_QUESTION.format(language=LANG_NAME.get(language, "English")),
            prompt, False, 80,
        )
        if raw and len(raw) < 180 and ("?" in raw or raw.endswith(("?", "？"))):
            return raw.strip()
        return None

    def explain(self, records: list[dict], risk_level: str, symptoms: list[str],
                language: str, safety_note: str, context: dict) -> dict | None:
        payload = {
            "RISK_LEVEL": risk_level,
            "SAFETY_NOTE": safety_note,
            "REPORTED_SYMPTOMS": symptoms,
            "USER_CONTEXT_(de-identified)": context,
            "RECORDS": [
                {
                    "id": r["ref"],
                    "problem": r["problem_en"],
                    "symptom": r["symptom_en"],
                    "remedy": r["remedy_en"],
                    "author": r["author"],
                    "book": r["book"],
                    "matched_symptoms": r.get("matched_symptoms", []),
                }
                for r in records
            ],
        }
        data = self._json(self._generate(
            SYSTEM_GROUNDED.format(language=LANG_NAME.get(language, "English")),
            json.dumps(payload, ensure_ascii=False),
            True, 1200,
        ))
        return data if isinstance(data, dict) else None

    def translate_remedy(self, text: str, language: str) -> str | None:
        return self._generate(
            SYSTEM_TRANSLATE.format(language=LANG_NAME.get(language, "English")),
            text, False, 500,
        )

    def summarise_external(self, results: list[dict], language: str,
                            symptoms: list[str]) -> str | None:
        system = (
            "Summarise the provided SNIPPETS from trusted health websites in "
            + LANG_NAME.get(language, "English")
            + ". Use ONLY the snippets. No dosages, no prescriptions, no treatment "
            "instructions, no diagnosis. 2–3 sentences of general education only. "
            "Mention that this is external information. Output plain text only."
        )
        payload = json.dumps(
            {
                "reported_symptoms": symptoms,
                "SNIPPETS": [
                    {"source": r["source"], "title": r["title"], "snippet": r["snippet"]}
                    for r in results
                ],
            },
            ensure_ascii=False,
        )
        return self._generate(system, payload, False, 500)


# ------------------------------------------------------------ output guards
_NUM = re.compile(r"\d+(?:[.,]\d+)?")
_ALLOWED_NUMS = {"108", "112", "14416", "1", "2", "3", "7", "14", "24", "48", "72"}
_INDIC_DIGITS = str.maketrans(
    "௦௧௨௩௪௫௬௭௮௯౦౧౨౩౪౫౬౭౮౯०१२३४५६७८९",
    "01234567890123456789" + "0123456789",
)


def numbers_in(text: str) -> list[str]:
    t = (text or "").translate(_INDIC_DIGITS)
    return [n.replace(",", ".") for n in _NUM.findall(t)]


def numbers_preserved(source: str, translation: str) -> bool:
    return sorted(numbers_in(source)) == sorted(numbers_in(translation))


def validate_explanation(data: dict | None, refs: set[str],
                          records_text: str, user_text: str) -> dict | None:
    """Reject LLM output that cites unknown records or introduces hallucinated numbers."""
    if not data or not isinstance(data.get("summary"), str):
        return None
    allowed = set(numbers_in(records_text)) | set(numbers_in(user_text)) | _ALLOWED_NUMS
    blob = " ".join(
        [data.get("summary", ""), data.get("care_note", "") or ""]
        + [str(w.get("reason", "")) for w in data.get("why_matched", []) if isinstance(w, dict)]
    )
    if any(n not in allowed for n in numbers_in(blob)):
        return None
    cited = set(re.findall(r"\[?(R\d+)\]?", blob))
    if cited - refs:
        return None
    for w in data.get("why_matched", []) or []:
        if not isinstance(w, dict) or w.get("id") not in refs:
            return None
    return data
