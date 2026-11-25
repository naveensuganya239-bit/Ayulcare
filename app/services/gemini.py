"""Gemini wrapper (server-side only)."""

from __future__ import annotations

import json
import logging
import math
import re

log = logging.getLogger(__name__)

LANG_NAME = {
    "en": "English",
    "ta": "Tamil",
    "te": "Telugu",
    "hi": "Hindi",
}


SYSTEM_GROUNDED = """\
You are the Ayurvedic remedy explanation layer in a health-information research prototype.

HARD RULES:
1. Use ONLY the supplied RECORDS. Never invent remedies, ingredients, quantities,
   dosages, durations, contraindications, or sources.
2. Never diagnose or claim that a remedy is effective, proven, safe, or a cure.
   Use phrases such as "the records describe" or "the book mentions".
3. Cite records only by their supplied IDs. Never invent IDs or book details.
4. Respect RISK_LEVEL:
   - low: summarize the records cautiously.
   - medium: provide at most one sentence of book information and encourage
     consultation with a qualified doctor.
   - high: do not present or summarize remedies. Follow SAFETY_NOTE and
     emphasize prompt medical assessment.
5. Do not repeat SAFETY_NOTE word-for-word.
6. Reply in {language}. Preserve medical terms and source numbers.
7. Describe what the records say. Do not turn historical descriptions into
   instructions for the user.
8. For low risk, use 3-5 sentences. For medium/high risk, be shorter.
9. Output ONLY valid JSON:
{{
    "summary": "<grounded summary>",
    "why_matched": [
        {{"id": "R1", "reason": "<why this record matches>"}}
    ],
    "care_note": "<one care sentence>"
}}
"""


SYSTEM_EXTRACT = """\
Extract structured symptom data from the patient's message.
The message may be in English, Tamil, Telugu, Hindi, or a mixture.

Recognise Ayurvedic problem names such as vata, pitta, gulma,
aruchi, or hikka as possible_problem_name hints.

Do not diagnose or give advice.
Use only information explicitly stated by the patient.

Return ONLY valid JSON with exactly these keys:
{{
    "symptoms": ["short English symptom terms, lowercase"],
    "negated_symptoms": ["symptoms explicitly denied"],
    "duration_days": <number or null>,
    "severity": "mild" | "moderate" | "severe" | null,
    "temperature_celsius": <number 34-43 or null>,
    "worsening": true | false,
    "for_someone_else": true | false,
    "patient_age_years": <number 0-120 or null>,
    "possible_problem_name": "<name or null>"
}}

Use null for unknown values. Do not infer missing information.
"""


SYSTEM_TRANSLATE = """\
Translate the following traditional Ayurvedic remedy text into {language}.

Rules:
- Preserve ingredient names, quantities, units, numbers, and warnings.
- Transliterate Sanskrit/Ayurvedic ingredient names rather than translating them.
- Do not add, omit, or reinterpret information.
- Output only the translated text.
"""

SYSTEM_TRANSLATE_BATCH = """\
Translate each traditional Ayurvedic remedy text into {language}.

Rules:
- Preserve ingredient names, quantities, units, numbers, and warnings.
- Transliterate Sanskrit/Ayurvedic ingredient names rather than translating them.
- Do not add, omit, or reinterpret information.
- Return one translation for every input, using the same index.
- Output ONLY valid JSON in this shape:
{{"translations": [{{"index": 0, "text": "translated text"}}]}}
"""


SYSTEM_QUESTION = """\
You assist a symptom-intake chatbot.

Generate exactly ONE short, neutral, clinically useful follow-up question
in {language} to better understand the main symptom.

Constraints:
- Do not diagnose, prescribe, or advise treatment.
- Do not repeat a question in ALREADY_ASKED.
- Use no more than 15 words.
- Output only the question.
"""


class GeminiClient:

    def __init__(self, api_key: str, model: str, timeout: int = 10):
        self.api_key = (api_key or "").strip()
        self.model = model
        self.timeout = max(1, int(timeout))
        self._client = None

    @property
    def enabled(self) -> bool:
        return bool(
            self.api_key
            and self.api_key not in {
                "YOUR_GEMINI_API_KEY_HERE",
                "your-api-key-here",
            }
        )

    def _get(self):
        if self._client is None:
            from google import genai
            from google.genai import types

            self._client = genai.Client(
                api_key=self.api_key,
                http_options=types.HttpOptions(
                    timeout=self.timeout * 1000
                ),
            )

        return self._client

    def _generate(
        self,
        system: str,
        user: str,
        json_mode: bool,
        max_tokens: int = 900,
    ) -> str | None:

        if not self.enabled:
            log.debug("Gemini disabled: no valid API key.")
            return None

        try:
            from google.genai import types

            config = types.GenerateContentConfig(
                system_instruction=system,
                temperature=0.1,
                max_output_tokens=max_tokens,
                response_mime_type=(
                    "application/json" if json_mode else "text/plain"
                ),
            )

            response = self._get().models.generate_content(
                model=self.model,
                contents=user,
                config=config,
            )

            result = (response.text or "").strip()
            return result or None

        except Exception as exc:
            exc_type = type(exc).__name__
            message = str(exc)

            if "API_KEY_INVALID" in message or "API key not valid" in message:
                log.error("Invalid Gemini API key. Check GEMINI_API_KEY.")

            elif "QUOTA_EXCEEDED" in message or "quota" in message.lower():
                log.warning("Gemini quota exceeded. Using fallback.")

            elif "MODEL_NOT_FOUND" in message or "not found" in message.lower():
                log.error("Gemini model '%s' was not found.", self.model)

            elif "SAFETY" in message:
                log.warning("Gemini safety filter blocked the response.")

            else:
                log.warning(
                    "Gemini request failed (%s): %s",
                    exc_type,
                    message[:200],
                )

            if exc_type in {
                "ConnectTimeout",
                "ReadTimeout",
                "ConnectionError",
            }:
                self._client = None

            return None

    @staticmethod
    def _json(raw: str | None):

        if not raw:
            return None

        cleaned = raw.strip()

        cleaned = re.sub(
            r"^\s*```(?:json)?\s*",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )

        cleaned = re.sub(r"\s*```\s*$", "", cleaned)

        try:
            return json.loads(cleaned)

        except json.JSONDecodeError:
            decoder = json.JSONDecoder()

            for index, character in enumerate(cleaned):
                if character == "{":
                    try:
                        result, _ = decoder.raw_decode(cleaned[index:])
                        return result
                    except json.JSONDecodeError:
                        continue

        return None

    @staticmethod
    def _valid_number(value, minimum=None, maximum=None):

        if isinstance(value, bool):
            return False

        if not isinstance(value, (int, float)):
            return False

        if not math.isfinite(value):
            return False

        if minimum is not None and value < minimum:
            return False

        if maximum is not None and value > maximum:
            return False

        return True

    # ---------------------------------------------------------
    # SYMPTOM EXTRACTION
    # ---------------------------------------------------------

    def extract(self, text: str, ctx_summary: str = "") -> dict | None:

        prompt = (
            f"KNOWN_SYMPTOMS_SO_FAR: {ctx_summary}\n"
            f"NEW_PATIENT_MESSAGE: {text}"
        )

        data = self._json(
            self._generate(
                SYSTEM_EXTRACT,
                prompt,
                True,
                500,
            )
        )

        if not isinstance(data, dict):
            return None

        symptoms = data.get("symptoms")
        negated = data.get("negated_symptoms")

        if not isinstance(symptoms, list):
            symptoms = []

        if not isinstance(negated, list):
            negated = []

        duration = data.get("duration_days")
        temperature = data.get("temperature_celsius")
        age = data.get("patient_age_years")
        severity = data.get("severity")
        problem_name = data.get("possible_problem_name")

        return {
            "symptoms": [
                item.strip().lower()[:60]
                for item in symptoms
                if isinstance(item, str) and item.strip()
            ][:10],

            "negated": [
                item.strip().lower()[:60]
                for item in negated
                if isinstance(item, str) and item.strip()
            ][:10],

            "duration_days": (
                duration
                if self._valid_number(duration, minimum=0)
                else None
            ),

            "severity": (
                severity
                if severity in {"mild", "moderate", "severe"}
                else None
            ),

            "fever_c": (
                temperature
                if self._valid_number(
                    temperature,
                    minimum=34,
                    maximum=43,
                )
                else None
            ),

            "worsening": (
                data.get("worsening")
                if isinstance(data.get("worsening"), bool)
                else False
            ),

            "other_subject": (
                data.get("for_someone_else")
                if isinstance(data.get("for_someone_else"), bool)
                else False
            ),

            "patient_age_years": (
                age
                if self._valid_number(age, minimum=0, maximum=120)
                else None
            ),

            "problem_hint": (
                problem_name.strip()[:100]
                if isinstance(problem_name, str) and problem_name.strip()
                else None
            ),
        }

    # ---------------------------------------------------------
    # CLARIFYING QUESTION
    # ---------------------------------------------------------

    def clarifying_question(
        self,
        symptoms: list[str],
        language: str,
        already_asked: list[str],
    ) -> str | None:

        prompt = (
            f"REPORTED_SYMPTOMS: {', '.join(symptoms)}\n"
            f"ALREADY_ASKED: {json.dumps(already_asked, ensure_ascii=False)}"
        )

        raw = self._generate(
            SYSTEM_QUESTION.format(
                language=LANG_NAME.get(language, "English")
            ),
            prompt,
            False,
            80,
        )

        if not raw:
            return None

        question = raw.strip().strip('"')

        if (
            len(question) < 180
            and len(question.split()) <= 15
            and ("?" in question or question.endswith("؟"))
        ):
            return question

        return None

    # ---------------------------------------------------------
    # GROUNDED REMEDY EXPLANATION
    # ---------------------------------------------------------

    def explain(
        self,
        records: list[dict],
        risk_level: str,
        symptoms: list[str],
        language: str,
        safety_note: str,
        context: dict,
    ) -> dict | None:

        payload = {
            "RISK_LEVEL": risk_level,
            "SAFETY_NOTE": safety_note,
            "REPORTED_SYMPTOMS": symptoms,
            "USER_CONTEXT_(de-identified)": context,

            "RECORDS": [
                {
                    "id": record["ref"],
                    "problem": record["problem_en"],
                    "symptom": record["symptom_en"],
                    "remedy": record["remedy_en"],
                    "author": record["author"],
                    "book": record["book"],
                    "matched_symptoms": record.get(
                        "matched_symptoms", []
                    ),
                }
                for record in records
            ],
        }

        data = self._json(
            self._generate(
                SYSTEM_GROUNDED.format(
                    language=LANG_NAME.get(language, "English")
                ),
                json.dumps(payload, ensure_ascii=False),
                True,
                1200,
            )
        )

        return data if isinstance(data, dict) else None

    # ---------------------------------------------------------
    # REMEDY TRANSLATION
    # ---------------------------------------------------------

    def translate_remedy(
        self,
        text: str,
        language: str,
    ) -> str | None:

        return self._generate(
            SYSTEM_TRANSLATE.format(
                language=LANG_NAME.get(language, "English")
            ),
            text,
            False,
            500,
        )

    def translate_remedies(
        self,
        texts: list[str],
        language: str,
    ) -> list[str | None]:
        if not texts:
            return []

        payload = json.dumps(
            [{"index": index, "text": text} for index, text in enumerate(texts)],
            ensure_ascii=False,
        )
        data = self._json(
            self._generate(
                SYSTEM_TRANSLATE_BATCH.format(
                    language=LANG_NAME.get(language, "English")
                ),
                payload,
                True,
                min(5000, 500 * len(texts)),
            )
        )

        translations: list[str | None] = [None] * len(texts)
        if not isinstance(data, dict) or not isinstance(data.get("translations"), list):
            return translations

        seen: set[int] = set()
        for item in data["translations"]:
            if not isinstance(item, dict):
                continue
            index = item.get("index")
            text = item.get("text")
            if (
                isinstance(index, bool)
                or not isinstance(index, int)
                or index < 0
                or index >= len(texts)
                or index in seen
                or not isinstance(text, str)
            ):
                continue
            seen.add(index)
            translated = text.strip()
            if translated and numbers_preserved(texts[index], translated):
                translations[index] = translated

        return translations

    # ---------------------------------------------------------
    # EXTERNAL INFORMATION SUMMARY
    # ---------------------------------------------------------

    def summarise_external(
        self,
        results: list[dict],
        language: str,
        symptoms: list[str],
    ) -> str | None:

        system = (
            "Summarise the provided SNIPPETS from trusted health websites in "
            + LANG_NAME.get(language, "English")
            + ". Use ONLY the snippets. No dosages, prescriptions, treatment "
            "instructions, or diagnosis. Give 2-3 sentences of general "
            "education. Mention that this is external information. "
            "Output plain text only."
        )

        payload = json.dumps(
            {
                "reported_symptoms": symptoms,

                "SNIPPETS": [
                    {
                        "source": result["source"],
                        "title": result["title"],
                        "snippet": result["snippet"],
                    }
                    for result in results
                ],
            },
            ensure_ascii=False,
        )

        return self._generate(
            system,
            payload,
            False,
            500,
        )


# ---------------------------------------------------------
# OUTPUT VALIDATION
# ---------------------------------------------------------

_NUM = re.compile(r"\d+(?:[.,]\d+)?")

_ALLOWED_NUMS = {
    "108",
    "112",
    "14416",
    "1",
    "2",
    "3",
    "7",
    "14",
    "24",
    "48",
    "72",
}

_INDIC_DIGITS = str.maketrans(
    "௦௧௨௩௪௫௬௭௮௯౦౧౨౩౪౫౬౭౮౯०१२३४५६७८९",
    "01234567890123456789" + "0123456789",
)


def numbers_in(text: str) -> list[str]:

    translated = (text or "").translate(_INDIC_DIGITS)

    return [
        number.replace(",", ".")
        for number in _NUM.findall(translated)
    ]


def numbers_preserved(source: str, translation: str) -> bool:

    return sorted(numbers_in(source)) == sorted(numbers_in(translation))


def validate_explanation(
    data: dict | None,
    refs: set[str],
    records_text: str,
    user_text: str,
) -> dict | None:
    """Reject explanations containing unknown record IDs or numbers."""

    if not isinstance(data, dict):
        return None

    summary = data.get("summary")

    if not isinstance(summary, str):
        return None

    why_matched = data.get("why_matched", [])

    if not isinstance(why_matched, list):
        return None

    care_note = data.get("care_note")

    if care_note is not None and not isinstance(care_note, str):
        return None

    allowed_numbers = (
        set(numbers_in(records_text))
        | set(numbers_in(user_text))
        | _ALLOWED_NUMS
    )

    reasons = []

    for item in why_matched:

        if not isinstance(item, dict):
            return None

        if not isinstance(item.get("id"), str):
            return None

        if item["id"] not in refs:
            return None

        if not isinstance(item.get("reason"), str):
            return None

        reasons.append(item["reason"])

    text_to_check = " ".join(
        [summary, care_note or ""] + reasons
    )

    if any(
        number not in allowed_numbers
        for number in numbers_in(text_to_check)
    ):
        return None

    cited_ids = set(
        re.findall(r"\bR\d+\b", text_to_check)
    )

    if cited_ids - refs:
        return None

    return data