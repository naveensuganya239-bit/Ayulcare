"""PII scrubbing and de-identified context building for external services."""
from __future__ import annotations

import re
from datetime import date

_PATTERNS = [
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "[email]"),
    (re.compile(r"(?<!\d)(?:\+?\d{1,3}[\s-]?)?(?:\d[\s-]?){9,12}(?!\d)"), "[number]"),
    (re.compile(r"https?://\S+"), "[link]"),
]


def scrub(text: str, extra_names: list[str] | None = None) -> str:
    out = text or ""
    for pat, repl in _PATTERNS:
        out = pat.sub(repl, out)
    for name in extra_names or []:
        for part in re.split(r"\s+", (name or "").strip()):
            if len(part) >= 3:
                out = re.sub(re.escape(part), "[name]", out, flags=re.I)
    return out


def age_years(dob: date | None, today: date | None = None) -> float | None:
    if not dob:
        return None
    today = today or date.today()
    years = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
    return float(max(years, 0))


def age_band(years: float | None) -> str | None:
    if years is None:
        return None
    if years < 1:
        return "infant"
    if years < 13:
        return "child"
    if years < 18:
        return "adolescent"
    if years < 40:
        return "adult 18-39"
    if years < 65:
        return "adult 40-64"
    return "older adult 65+"


def ai_safe_context(profile, share_health: bool) -> dict:
    """Minimal context allowed to leave the server. NEVER includes name, contact,
    city/area, date of birth, email or any identifier. Chronic-condition text is shared
    only when the user opted in to 'personalise with my health profile'."""
    if not profile or not share_health:
        return {}
    ctx = {"age_band": age_band(age_years(profile.date_of_birth))}
    if profile.chronic_conditions:
        ctx["long_term_conditions"] = scrub(profile.chronic_conditions)[:200]
    if profile.food_preference:
        ctx["food_preference"] = profile.food_preference
    return {k: v for k, v in ctx.items() if v}
