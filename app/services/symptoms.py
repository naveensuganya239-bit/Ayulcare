"""Rule-based natural-language understanding of symptom descriptions.

This lexicon is a *language-understanding aid* (mapping surface forms in EN/TA/TE/HI
to canonical English symptom terms, durations, severity, temperature). It is not a
medical knowledge base and it never produces diagnoses. It is the offline fallback
and the safety net that complements Gemini-based extraction.
The multilingual surface forms should be reviewed by native speakers / clinicians.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

LEXICON: dict[str, dict[str, list[str]]] = {
    "fever": {"en": ["fever", "temperature", "feverish", "high temp"], "ta": ["காய்ச்சல்", "சுரம்"], "te": ["జ్వరం", "జ్వరము"], "hi": ["बुखार", "ज्वर"]},
    "cough": {"en": ["cough", "coughing"], "ta": ["இருமல்"], "te": ["దగ్గు"], "hi": ["खांसी", "खाँसी"]},
    "cold": {"en": ["common cold", "cold and", "have a cold", "got a cold", "congestion", "blocked nose"], "ta": ["சளி"], "te": ["జలుబు"], "hi": ["जुकाम", "सर्दी", "ज़ुकाम"]},
    "runny nose": {"en": ["runny nose", "running nose", "nasal discharge"], "ta": ["மூக்கு ஒழுகு", "மூக்கில் நீர்"], "te": ["ముక్కు కారు"], "hi": ["नाक बह"]},
    "sneezing": {"en": ["sneez"], "ta": ["தும்மல்"], "te": ["తుమ్ము"], "hi": ["छींक"]},
    "sore throat": {"en": ["sore throat", "throat pain", "throat irritation", "throat ache", "scratchy throat", "itchy throat", "throat infection"], "ta": ["தொண்டை வலி", "தொண்டை கரகர", "தொண்டை எரிச்சல்", "தொண்டை புண்"], "te": ["గొంతు నొప్పి", "గొంతు మంట", "గొంతు గరగర"], "hi": ["गले में दर्द", "गले में खराश", "गला खराब", "गले में जलन", "गले में खरास"]},
    "headache": {"en": ["headache", "head ache", "head pain"], "ta": ["தலைவலி", "தலை வலி"], "te": ["తలనొప్పి", "తల నొప్పి"], "hi": ["सिरदर्द", "सिर दर्द", "सर दर्द", "सिर में दर्द"]},
    "body pain": {"en": ["body pain", "body ache", "body aches", "muscle pain", "myalgia"], "ta": ["உடல் வலி", "உடல்வலி", "தசை வலி"], "te": ["ఒళ్ళు నొప్పులు", "ఒంటి నొప్పులు", "కండరాల నొప్పి"], "hi": ["बदन दर्द", "शरीर दर्द", "शरीर में दर्द", "मांसपेशियों में दर्द"]},
    "stomach pain": {"en": ["stomach pain", "stomach ache", "abdominal pain", "belly pain", "tummy ache", "stomachache"], "ta": ["வயிற்று வலி", "வயிறு வலி", "வயிற்றில் வலி"], "te": ["కడుపు నొప్పి", "పొట్ట నొప్పి"], "hi": ["पेट दर्द", "पेट में दर्द", "पेट मे दर्द"]},
    "nausea": {"en": ["nausea", "nauseous", "feel like vomiting", "queasy"], "ta": ["குமட்டல்"], "te": ["వికారం"], "hi": ["मतली", "जी मिचल"]},
    "vomiting": {"en": ["vomit", "throwing up", "threw up"], "ta": ["வாந்தி"], "te": ["వాంతి", "వాంతులు"], "hi": ["उल्टी"]},
    "diarrhea": {"en": ["diarrhea", "diarrhoea", "loose motion", "loose stool", "watery stool"], "ta": ["வயிற்றுப்போக்கு", "வயிற்றுப் போக்கு", "பேதி"], "te": ["విరేచనాలు"], "hi": ["दस्त", "पतला पखाना", "लूज मोशन"]},
    "constipation": {"en": ["constipat", "hard stool"], "ta": ["மலச்சிக்கல்"], "te": ["మలబద్ధకం"], "hi": ["कब्ज"]},
    "acidity": {"en": ["acidity", "acid reflux", "heartburn", "indigestion", "gas trouble", "bloating", "bloated"], "ta": ["அஜீரணம்", "நெஞ்செரிச்சல்", "அசிடிட்டி", "வாயு தொல்லை"], "te": ["అజీర్ణం", "ఎసిడిటీ", "గ్యాస్"], "hi": ["अपच", "एसिडिटी", "गैस", "सीने में जलन", "अम्लता"]},
    "loss of appetite": {"en": ["loss of appetite", "no appetite", "not hungry", "don't feel like eating"], "ta": ["பசியின்மை", "பசி இல்லை"], "te": ["ఆకలి లేకపోవడం", "ఆకలి లేదు"], "hi": ["भूख न लगना", "भूख नहीं", "भूख कम"]},
    "fatigue": {"en": ["fatigue", "tired", "tiredness", "weakness", "weak ", "exhausted", "lethargic"], "ta": ["சோர்வு", "களைப்பு", "பலவீனம்"], "te": ["అలసట", "నీరసం", "బలహీనత"], "hi": ["थकान", "कमजोरी", "थकावट"]},
    "dizziness": {"en": ["dizzy", "dizziness", "giddy", "light-headed", "lightheaded"], "ta": ["தலைச்சுற்றல்", "தலை சுற்றல்", "மயக்கம்"], "te": ["తల తిరగ", "తలతిరుగుడు"], "hi": ["चक्कर"]},
    "joint pain": {"en": ["joint pain", "joint ache", "knee pain", "arthritis"], "ta": ["மூட்டு வலி", "மூட்டுவலி"], "te": ["కీళ్ల నొప్పులు", "కీళ్ళ నొప్పులు", "మోకాళ్ల నొప్పి"], "hi": ["जोड़ों का दर्द", "जोड़ों में दर्द", "घुटनों में दर्द"]},
    "back pain": {"en": ["back pain", "backache", "lower back"], "ta": ["முதுகு வலி", "முதுகுவலி", "இடுப்பு வலி"], "te": ["నడుము నొప్పి", "వెన్ను నొప్పి", "వెన్నునొప్పి"], "hi": ["कमर दर्द", "पीठ दर्द", "कमर में दर्द", "पीठ में दर्द"]},
    "itching": {"en": ["itching", "itchy", "itch"], "ta": ["அரிப்பு"], "te": ["దురద"], "hi": ["खुजली"]},
    "skin rash": {"en": ["rash", "skin allergy", "hives"], "ta": ["தடிப்பு", "தோல் அலர்ஜி"], "te": ["దద్దుర్లు"], "hi": ["चकत्ते", "दाने", "रैश"]},
    "insomnia": {"en": ["insomnia", "can't sleep", "cannot sleep", "trouble sleeping", "sleeplessness", "unable to sleep"], "ta": ["தூக்கமின்மை", "தூக்கம் வரவில்லை", "தூக்கம் இல்லை"], "te": ["నిద్రలేమి", "నిద్ర రావడం లేదు"], "hi": ["नींद न आना", "अनिद्रा", "नींद नहीं आ"]},
    "burning urination": {"en": ["burning urination", "burning while urinating", "painful urination", "burning sensation while passing urine"], "ta": ["சிறுநீர் எரிச்சல்", "சிறுநீர் கழிக்கும் போது எரிச்சல்"], "te": ["మూత్రంలో మంట", "మూత్ర విసర్జనలో మంట"], "hi": ["पेशाब में जलन", "पेशाब मे जलन"]},
    "breathlessness": {"en": ["breathless", "shortness of breath", "difficulty breathing"], "ta": ["மூச்சுத்திணறல்", "மூச்சு விட சிரமம்"], "te": ["ఊపిరి ఆడకపోవడం"], "hi": ["सांस फूल", "साँस फूल", "सांस लेने में"]},
    "chest pain": {"en": ["chest pain", "chest tightness"], "ta": ["நெஞ்சு வலி", "மார்பு வலி"], "te": ["ఛాతీ నొప్పి", "ఛాతి నొప్పి"], "hi": ["सीने में दर्द", "छाती में दर्द"]},
    # --- Extended Ayurvedic / common symptom terms ---
    "ear pain": {"en": ["ear pain", "ear ache", "earache", "ear infection"], "ta": ["காது வலி", "காது வலிக்கிறது"], "te": ["చెవి నొప్పి"], "hi": ["कान में दर्द", "कान दर्द"]},
    "eye irritation": {"en": ["eye irritation", "red eye", "watery eyes", "eye pain", "burning eyes"], "ta": ["கண் எரிச்சல்", "கண் சிவப்பு"], "te": ["కంటి మంట", "కళ్ళు ఎర్రబడ్డాయి"], "hi": ["आँख में जलन", "आंख में जलन", "आंखें लाल"]},
    "swelling": {"en": ["swelling", "swollen", "puffiness", "oedema", "edema"], "ta": ["வீக்கம்", "வீங்கி"], "te": ["వాపు", "వాచిపోయింది"], "hi": ["सूजन", "सूजा हुआ"]},
    "worm infection": {"en": ["worm", "intestinal worm", "parasite"], "ta": ["புழு", "குடல் புழு"], "te": ["పురుగులు", "పేగు పురుగులు"], "hi": ["कीड़े", "पेट में कीड़े"]},
    "acne": {"en": ["acne", "pimple", "pimples", "breakout"], "ta": ["முகப்பரு", "பரு"], "te": ["మొటిమలు"], "hi": ["मुंहासे", "पिंपल"]},
    "hair loss": {"en": ["hair loss", "hair fall", "balding", "alopecia"], "ta": ["முடி உதிர்வு", "முடி கொட்டுகிறது"], "te": ["జుట్టు రాలడం", "వెంట్రుకలు రాలుతున్నాయి"], "hi": ["बाल झड़ना", "बाल गिरना", "बाल झड़"]},
    "low immunity": {"en": ["low immunity", "weak immunity", "frequent infections", "fall sick often"], "ta": ["குறைந்த நோய் எதிர்ப்பு", "நோய் எதிர்ப்பு சக்தி குறைவு"], "te": ["రోగనిరోధకత తక్కువ"], "hi": ["कमजोर रोग प्रतिरोधक", "इम्यूनिटी कमजोर"]},
    "bloating": {"en": ["bloat", "bloating", "flatulence", "gas", "gassy", "distension"], "ta": ["வயிறு உப்புசம்", "வாயு"], "te": ["గ్యాస్ ట్రబుల్", "పొట్ట ఉబ్బరం"], "hi": ["पेट फूलना", "गैस बनना", "अफरा"]},
    "hiccups": {"en": ["hiccup", "hiccoughs"], "ta": ["விக்கல்"], "te": ["దొక్కు"], "hi": ["हिचकी"]},
    "loss of taste": {"en": ["loss of taste", "no taste", "can't taste"], "ta": ["சுவை இழப்பு", "சுவை தெரியவில்லை"], "te": ["రుచి తెలియడం లేదు"], "hi": ["स्वाद नहीं आना", "खाने का स्वाद नहीं"]},
    "abdominal pain": {"en": ["abdominal pain", "abdomen pain", "gulma", "colic"], "ta": ["வயிற்று வலி", "வயிறு வலி"], "te": ["పొట్ట నొప్పి", "కడుపు నొప్పి"], "hi": ["पेट में दर्द", "उदर दर्द"]},
    "pitta": {"en": ["pitta", "body heat", "heat in body", "burning sensation inside"], "ta": ["பித்தம்", "உடல் வெப்பம்"], "te": ["పిత్తం", "శరీరంలో వేడి"], "hi": ["पित्त", "शरीर में गर्मी", "जलन"]},
    "vata": {"en": ["vata", "joint stiffness", "dry skin", "irregular digestion"], "ta": ["வாதம்"], "te": ["వాత వ్యాధి"], "hi": ["वात", "जोड़ों में कठोरता"]},
    "kapha": {"en": ["kapha", "mucus excess", "heaviness", "congestion", "mucus"], "ta": ["கபம்", "சளி அதிகம்"], "te": ["కఫం", "శ్లేష్మం"], "hi": ["कफ", "बलगम", "भारीपन"]},
}

_NEG_EN = re.compile(r"\b(no|not|without|never|denies|don't have|do not have|dont have|haven't|have not|free of)\b(\s+\w+){0,3}?\s*$")
_NUM_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "a": 1, "an": 1, "couple": 2, "few": 3,
              "ஒரு": 1, "இரண்டு": 2, "மூன்று": 3, "நான்கு": 4, "ஐந்து": 5, "ஆறு": 6, "ஏழு": 7, "எட்டு": 8, "ஒன்பது": 9, "பத்து": 10,
              "ఒక": 1, "రెండు": 2, "మూడు": 3, "నాలుగు": 4, "ఐదు": 5, "ఆరు": 6, "ఏడు": 7, "ఎనిమిది": 8, "తొమ్మిది": 9, "పది": 10,
              "एक": 1, "दो": 2, "तीन": 3, "चार": 4, "पांच": 5, "पाँच": 5, "छह": 6, "छः": 6, "सात": 7, "आठ": 8, "नौ": 9, "दस": 10}
_UNIT_DAYS = {"hour": 1 / 24, "day": 1, "week": 7, "month": 30, "year": 365}
_UNIT_RE = {
    "en": r"(hour|hr|day|week|month|year)s?",
    "ta": r"(மணி நேர|மணிநேர|நாட்கள|நாள்|நாளா|வாரங்கள|வாரம்|வாரமா|மாதங்கள|மாதம்|மாதமா)",
    "te": r"(గంటలు|గంట|రోజులు|రోజు|వారాలు|వారం|నెలలు|నెల)",
    "hi": r"(घंटे|घंटा|दिन|हफ्ते|हफ़्ते|सप्ताह|हफ्ता|महीने|महीना)",
}
_INDIC_UNIT_MAP = {
    "மணி நேர": "hour", "மணிநேர": "hour", "நாட்கள": "day", "நாள்": "day", "நாளா": "day", "வாரங்கள": "week", "வாரம்": "week", "வாரமா": "week", "மாதங்கள": "month", "மாதம்": "month", "மாதமா": "month",
    "గంటలు": "hour", "గంట": "hour", "రోజులు": "day", "రోజు": "day", "వారాలు": "week", "వారం": "week", "నెలలు": "month", "నెల": "month",
    "घंटे": "hour", "घंटा": "hour", "दिन": "day", "हफ्ते": "week", "हफ़्ते": "week", "सप्ताह": "week", "हफ्ता": "week", "महीने": "month", "महीना": "month",
}
_SEVERE = ["severe", "unbearable", "very bad", "excruciating", "intense", "terrible", "கடுமையான", "தாங்க முடியாத", "மிகவும் அதிக", "తీవ్రమైన", "భరించలేని", "చాలా ఎక్కువ", "बहुत तेज", "असहनीय", "गंभीर", "बहुत ज्यादा"]
_MODERATE = ["moderate", "manageable", "medium", "நடுத்தர", "மிதமான", "మధ్యస్థ", "మోస్తరు", "मध्यम", "ठीक-ठाक", "सामान्य दर्द"]
_MILD = ["mild", "slight", "little", "minor", "light", "லேசான", "சிறிய", "கொஞ்சம்", "స్వల్ప", "కొద్దిగా", "తేలికపాటి", "हल्का", "हल्की", "थोड़ा", "थोड़ी", "मामूली"]
_WORSE = ["worse", "worsen", "getting worse", "increasing", "spreading", "not improving", "no improvement", "மோசமாக", "அதிகமாகிறது", "குணமாகவில்லை", "ఎక్కువవుతోంది", "తగ్గడం లేదు", "తీవ్రమవుతోంది", "बढ़ रहा", "बिगड़", "ठीक नहीं हो रहा", "आराम नहीं"]
_OTHER_SUBJECT = re.compile(r"\b(my|the)\s+(baby|infant|newborn|child|kid|son|daughter|mother|father|mom|dad|wife|husband|grandmother|grandfather|grandma|grandpa)\b|"
                            r"(என் (குழந்தை|மகன்|மகள்|அம்மா|அப்பா|மனைவி|கணவர்))|(నా (బిడ్డ|కొడుకు|కూతురు|అమ్మ|నాన్న))|(मेरा (बच्चा|बेटा|बेटी)|मेरी (माँ|मां|बेटी|पत्नी)|मेरे (पिता|पति))", re.I)
_YES = ["yes", "yeah", "yep", "yup", "i do", "have", "ஆம்", "ஆமாம்", "அவுனு", "అవును", "ఉంది", "हाँ", "हां", "जी हाँ", "जी हां", "है"]
_NO = ["no", "nope", "none", "nothing", "not really", "no symptoms", "இல்லை", "இல்ல", "லேது", "లేదు", "లేవు", "नहीं", "नही", "कोई नहीं"]


def norm(text: str) -> str:
    return unicodedata.normalize("NFKC", text or "").lower()


@dataclass
class Extraction:
    symptoms: list[str] = field(default_factory=list)
    negated: list[str] = field(default_factory=list)
    duration_days: float | None = None
    duration_text: str | None = None
    severity: str | None = None
    fever_c: float | None = None
    worsening: bool = False
    other_subject: bool = False
    patient_age_years: float | None = None
    yes_no: str | None = None
    method: str = "lexicon"


def _find_symptoms(t: str) -> tuple[list[str], list[str]]:
    found, negated = [], []
    for canon, forms in LEXICON.items():
        hit = None
        for lang_forms in forms.values():
            for f in lang_forms:
                i = t.find(f.lower())
                if i >= 0:
                    hit = i
                    break
            if hit is not None:
                break
        if hit is None:
            continue
        if _NEG_EN.search(t[max(0, hit - 40):hit]):
            negated.append(canon)
        else:
            found.append(canon)
    return found, negated


def _parse_duration(t: str) -> tuple[float | None, str | None]:
    if re.search(r"\b(since (this )?(morning|today)|today|just started|few hours|since last night)\b", t):
        return 0.5, "today"
    if re.search(r"\bsince yesterday|yesterday\b", t):
        return 1.0, "since yesterday"
    for lang, unit in _UNIT_RE.items():
        for m in re.finditer(rf"(\d+(?:\.\d+)?|{'|'.join(sorted(_NUM_WORDS, key=len, reverse=True))})\s*[-\s]*(?:to\s*\d+\s*)?{unit}", t):
            raw = m.group(1)
            n = float(raw) if raw[0].isdigit() else float(_NUM_WORDS[raw])
            u = m.group(2)
            key = _INDIC_UNIT_MAP.get(u, re.sub(r"s$", "", u).replace("hr", "hour"))
            if key in _UNIT_DAYS:
                return round(n * _UNIT_DAYS[key], 2), m.group(0).strip()
    return None, None


def _parse_temperature(t: str) -> float | None:
    m = re.search(r"(\d{2,3}(?:\.\d)?)\s*(?:°|º|degrees?)?\s*(f|c|fahrenheit|celsius)\b", t)
    if not m:
        return None
    v, u = float(m.group(1)), m.group(2)[0]
    if u == "f" and 90 <= v <= 110:
        return round((v - 32) * 5 / 9, 1)
    if u == "c" and 34 <= v <= 43:
        return v
    return None


def _parse_age(t: str) -> float | None:
    m = re.search(r"(\d+(?:\.\d+)?)\s*[- ]?(year|yr|month|week|day)s?\s*[- ]?old", t)
    if m:
        v, u = float(m.group(1)), m.group(2)
        return round(v / {"year": 1, "yr": 1, "month": 12, "week": 52, "day": 365}[u], 3)
    m = re.search(r"\b(?:age|aged)\s*(?:is\s*)?(\d{1,3})\b|\b(\d{1,3})\s*(?:years|yrs|வயது|ఏళ్ళు|సంవత్సరాల|साल|वर्ष)", t)
    if m:
        return float(m.group(1) or m.group(2))
    return None


def _any(t: str, words: list[str]) -> bool:
    return any(w in t for w in words)


def parse_yes_no(text: str) -> str | None:
    t = norm(text).strip(" .!?,")
    toks = set(re.findall(r"\w+", t))
    if any(w in t for w in _NO if " " in w or not w.isascii()) or (toks & {"no", "nope", "none", "nothing"}):
        return "no"
    if any(w in t for w in _YES if not w.isascii()) or (toks & {"yes", "yeah", "yep", "yup"}):
        return "yes"
    return None


def extract_rule_based(text: str) -> Extraction:
    t = norm(text)
    found, negated = _find_symptoms(t)
    days, dtext = _parse_duration(t)
    sev = "severe" if _any(t, _SEVERE) else "moderate" if _any(t, _MODERATE) else "mild" if _any(t, _MILD) else None
    return Extraction(
        symptoms=found, negated=negated, duration_days=days, duration_text=dtext, severity=sev,
        fever_c=_parse_temperature(t), worsening=_any(t, _WORSE), other_subject=bool(_OTHER_SUBJECT.search(t)),
        patient_age_years=_parse_age(t), yes_no=parse_yes_no(text), method="lexicon",
    )
