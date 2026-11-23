import pytest

from app.services.language import detect_language
from app.services.risk import assess, detect_red_flags
from app.services.symptoms import extract_rule_based


@pytest.mark.parametrize("text", [
    "I have chest pain", "எனக்கு நெஞ்சு வலி", "నాకు ఛాతీ నొప్పి", "मुझे सीने में दर्द है", "vomiting blood", "I want to die",
    "no fever but chest pain", "I have no relief, chest pain"])
def test_red_flags_high(text):
    assert assess(text).level == "high"


@pytest.mark.parametrize("text", ["I do not have chest pain", "no chest pain, just a runny nose"])
def test_negated_english_red_flags_not_triggered(text):
    assert detect_red_flags(text)[0] == []


def test_crisis_category():
    assert assess("I want to end my life").category == "crisis"


def test_medium_rules_and_infant():
    assert assess("x", symptoms=["fever"], duration_days=4).level == "medium"
    assert assess("x", symptoms=["cough"], duration_days=20).level == "medium"
    assert assess("x", symptoms=["fever"], duration_days=1, age_years=0.1).level == "high"
    assert assess("x", symptoms=["cough"], duration_days=2).level == "low"


def test_language_detection():
    assert detect_language("I have a headache").lang == "en"
    assert detect_language("எனக்கு தலைவலி உள்ளது").lang == "ta"
    assert detect_language("నాకు తలనొప్పి ఉంది").lang == "te"
    assert detect_language("मुझे सिरदर्द है").lang == "hi"
    assert detect_language("எனக்கு fever இருக்கு").mixed


def test_extraction_multilingual():
    e = extract_rule_based("எனக்கு 3 நாட்களாக இருமல் மற்றும் தொண்டை வலி")
    assert {"cough", "sore throat"} <= set(e.symptoms) and e.duration_days == 3
    e = extract_rule_based("no fever, cough for 2 weeks, 101 F")
    assert "cough" in e.symptoms and "fever" in e.negated and e.duration_days == 14
