"""Automatic language detection for English / Tamil / Telugu / Hindi.

Strategy (deterministic first, model second):
  1. Unicode-script analysis -- reliable for Tamil, Telugu, Devanagari (Hindi), Latin.
  2. Romanised-Indic marker words ("kaichal", "bukhar" ...) -> low-confidence hint.
  3. Mixed-script handling: the dominant non-Latin script wins (code-mixed queries are
     common: Tamil sentence + English drug/symptom words).
  4. Low confidence -> caller falls back to (manual selection) > (conversation language)
     > (profile language) > English, optionally asking Gemini.
Devanagari is mapped to Hindi (Marathi/Nepali share the script; documented limitation).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

SUPPORTED = ("en", "ta", "te", "hi")
NAMES = {"en": "English", "ta": "Tamil (தமிழ்)", "te": "Telugu (తెలుగు)", "hi": "Hindi (हिन्दी)"}
BCP47 = {"en": "en-IN", "ta": "ta-IN", "te": "te-IN", "hi": "hi-IN"}

_RANGES = {"ta": (0x0B80, 0x0BFF), "te": (0x0C00, 0x0C7F), "hi": (0x0900, 0x097F)}
_ROMAN_MARKERS = {
    "ta": {"kaichal", "irumal", "thalai", "vali", "vayiru", "valikkuthu", "enakku", "romba", "sali", "thondai", "udambu", "suram", "vandhi"},
    "hi": {"bukhar", "khansi", "sardi", "pet", "dard", "mujhe", "hai", "nahi", "bahut", "sir", "gala", "ulti", "dast", "kamzori"},
    "te": {"jwaram", "daggu", "tala", "noppi", "kadupu", "naaku", "undi", "chala", "jalubu", "vaanthi"},
}


@dataclass
class LangResult:
    lang: str
    confidence: float
    mixed: bool
    uncertain: bool
    scripts: dict
    method: str


def detect_language(text: str) -> LangResult:
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return LangResult("en", 0.0, False, True, {}, "empty")
    counts = {"en": 0, "ta": 0, "te": 0, "hi": 0, "other": 0}
    for c in letters:
        o = ord(c)
        for lang, (lo, hi) in _RANGES.items():
            if lo <= o <= hi:
                counts[lang] += 1
                break
        else:
            counts["en" if o < 0x250 else "other"] += 1
    total = len(letters)
    shares = {k: v / total for k, v in counts.items() if v}
    non_latin = {k: v for k, v in counts.items() if k in ("ta", "te", "hi") and v}
    if non_latin:
        lang = max(non_latin, key=non_latin.get)
        share = counts[lang] / total
        mixed = counts["en"] / total >= 0.15 or len(non_latin) > 1
        conf = min(1.0, 0.55 + share * 0.5) if share >= 0.25 else 0.5
        return LangResult(lang, round(conf, 2), mixed, conf < 0.7, shares, "script")
    # Latin only: English vs romanised Indic
    words = set(re.findall(r"[a-z]+", text.lower()))
    hits = {lang: len(words & m) for lang, m in _ROMAN_MARKERS.items()}
    best = max(hits, key=hits.get)
    if hits[best] >= 2 and hits[best] / max(len(words), 1) >= 0.25:
        return LangResult(best, 0.55, True, True, shares, "romanised")
    return LangResult("en", 0.9 if total >= 12 else 0.7, False, total < 6, shares, "script")


def resolve_reply_language(text: str, manual: str | None, conversation_lang: str | None,
                           profile_lang: str | None) -> tuple[str, LangResult]:
    """Decide the reply language. Manual selection wins; otherwise auto-detect with fallbacks."""
    det = detect_language(text)
    if manual and manual in SUPPORTED:
        return manual, det
    if not det.uncertain:
        return det.lang, det
    for fallback in (conversation_lang, profile_lang):
        if fallback in SUPPORTED:
            return fallback, det
    return (det.lang if det.lang in SUPPORTED else "en"), det
