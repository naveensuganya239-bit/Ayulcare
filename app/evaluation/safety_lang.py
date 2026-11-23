"""Safety (red-flag) and language-detection regression suites.

IMPORTANT: the built-in cases are ENGINEERING regression cases written by the developer.
They show that the rule engine behaves as designed; they are NOT a clinically validated
gold standard. For publication, replace/extend data/eval/safety_testcases.json with
cases reviewed by qualified clinicians and report their sensitivity/specificity.
"""
from __future__ import annotations

import json
from pathlib import Path

from ..services.language import detect_language
from ..services.risk import RULESET_VERSION, assess

DEFAULT_SAFETY = [
    # (text, expected_level, kwargs)
    ("I have severe chest pain spreading to my left arm", "high", {}),
    ("I can't breathe properly and my lips look blue", "high", {}),
    ("my father fainted and is not responding", "high", {}),
    ("I am vomiting blood", "high", {}),
    ("my face is drooping and my speech is slurred", "high", {}),
    ("I want to end my life", "high", {}),
    ("my lips and tongue are swelling after eating prawns", "high", {}),
    ("he swallowed pesticide", "high", {}),
    ("stiff neck and fever since morning", "high", {}),
    ("எனக்கு நெஞ்சு வலி மற்றும் மூச்சுத்திணறல்", "high", {}),
    ("மலத்தில் இரத்தம் வருகிறது", "high", {}),
    ("నాకు ఛాతీ నొప్పి ఉంది", "high", {}),
    ("నాకు ఊపిరి ఆడకపోవడం", "high", {}),
    ("मुझे सीने में दर्द और सांस लेने में तकलीफ है", "high", {}),
    ("उल्टी में खून आ रहा है", "high", {}),
    ("मैं आत्महत्या करना चाहता हूँ", "high", {}),
    ("fever of 104 F", "high", {"fever_c": 40.0, "symptoms": ["fever"]}),
    ("baby has fever", "high", {"age_years": 0.1, "symptoms": ["fever"]}),
    ("mild cough for two days", "low", {"symptoms": ["cough"], "duration_days": 2}),
    ("mild headache since morning", "low", {"symptoms": ["headache"], "duration_days": 0.5}),
    ("no chest pain, no breathing problem, just a runny nose", "low", {"symptoms": ["runny nose"], "duration_days": 2}),
    ("எனக்கு லேசான சளி உள்ளது", "low", {"symptoms": ["cold"], "duration_days": 1}),
    ("fever for 4 days", "medium", {"symptoms": ["fever"], "duration_days": 4}),
    ("cough for 3 weeks", "medium", {"symptoms": ["cough"], "duration_days": 21}),
    ("symptoms are getting worse", "medium", {"symptoms": ["cough"], "duration_days": 2, "worsening": True}),
    ("diarrhoea for 3 days", "medium", {"symptoms": ["diarrhea"], "duration_days": 3}),
    ("fever and cough in an older adult", "medium", {"symptoms": ["fever", "cough"], "duration_days": 1, "age_years": 70}),
    ("fever with diabetes", "medium", {"symptoms": ["fever"], "duration_days": 1, "chronic_text": "type 2 diabetes"}),
]

DEFAULT_LANG = [
    ("I have a fever and a cough since yesterday", "en"), ("My stomach hurts after eating", "en"),
    ("எனக்கு இரண்டு நாட்களாக காய்ச்சல் மற்றும் இருமல் உள்ளது", "ta"), ("வயிற்று வலி மற்றும் வாந்தி", "ta"),
    ("నాకు మూడు రోజులుగా జ్వరం మరియు దగ్గు ఉంది", "te"), ("తలనొప్పి మరియు గొంతు నొప్పి", "te"),
    ("मुझे दो दिन से बुखार और खांसी है", "hi"), ("पेट में दर्द और उल्टी हो रही है", "hi"),
    ("எனக்கு fever இருக்கு and தலைவலி", "ta"), ("मुझे headache और fever है", "hi"),
    ("నాకు cough ఉంది and జ్వరం", "te"),
]


def run_safety_eval(cfg) -> dict:
    path = Path(cfg["EVAL_DIR"]) / "safety_testcases.json"
    cases = [(c["text"], c["expected"], c.get("kwargs", {})) for c in json.loads(path.read_text(encoding="utf-8"))] if path.exists() else DEFAULT_SAFETY
    rows, tp = [], 0
    high_total = fn = fp = nonhigh_total = under = 0
    order = {"low": 0, "medium": 1, "high": 2}
    for text, expected, kw in cases:
        got = assess(text, **kw).level
        rows.append({"text": text, "expected": expected, "got": got, "ok": got == expected})
        if expected == "high":
            high_total += 1
            fn += got != "high"
        else:
            nonhigh_total += 1
            fp += got == "high"
        under += order[got] < order[expected]
    summary = {"ruleset": RULESET_VERSION, "n_cases": len(rows), "accuracy": round(sum(r["ok"] for r in rows) / len(rows), 4),
               "high_sensitivity": round(1 - fn / high_total, 4) if high_total else None,
               "false_high_rate_on_non_high": round(fp / nonhigh_total, 4) if nonhigh_total else None,
               "under_triage_cases": under, "caveat": "Engineering regression cases, not clinically validated."}
    return {"summary": summary, "rows": rows}


def run_language_eval(cfg) -> dict:
    rows = [{"text": t, "expected": e, "got": detect_language(t).lang} for t, e in DEFAULT_LANG]
    acc = sum(r["expected"] == r["got"] for r in rows) / len(rows)
    per = {}
    for lg in ("en", "ta", "te", "hi"):
        sub = [r for r in rows if r["expected"] == lg]
        per[lg] = round(sum(r["expected"] == r["got"] for r in sub) / len(sub), 3) if sub else None
    return {"summary": {"n": len(rows), "accuracy": round(acc, 4), "per_language": per,
                        "caveat": "Small developer-authored set; extend with real user-style and code-mixed samples."}, "rows": rows}
