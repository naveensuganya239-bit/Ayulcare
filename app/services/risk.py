"""Deterministic, language-model-independent risk assessment.

!!! CLINICAL REVIEW REQUIRED !!!
RULESET_VERSION marks this rule set as a conservative DRAFT assembled from widely
published red-flag symptom categories. It has NOT been validated by clinicians.
Before any real-world use (and before reporting safety results) it must be
reviewed and signed off by qualified healthcare professionals. The dataset's own
Low/Medium/High labels are deliberately NOT used here.

The engine never calls an LLM. Gemini cannot raise, lower, or override the result.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .symptoms import norm

RULESET_VERSION = "0.1-draft-awaiting-clinical-review"

# ---------------------------------------------------------------- HIGH rules
# Each entry: id -> (category, {lang: regex})   category: emergency | crisis
HIGH_RULES: dict[str, tuple[str, dict[str, str]]] = {
    "chest_pain": ("emergency", {
        "en": r"chest (pain|tightness|pressure|discomfort)|pressure in (my )?chest|heart attack|pain in (my )?chest",
        "ta": r"நெஞ்சு வலி|நெஞ்சில் வலி|மார்பு வலி|நெஞ்சு இறுக்கம்|நெஞ்சு அழுத்தம்",
        "te": r"ఛాతీ నొప్పి|ఛాతి నొప్పి|గుండె నొప్పి|గుండెల్లో నొప్పి|ఛాతీలో బిగుతు",
        "hi": r"सीने में दर्द|छाती में दर्द|सीने में जकड़न|सीने में भारीपन|दिल का दौरा|छाती में जकड़न"}),
    "breathing_difficulty": ("emergency", {
        "en": r"difficulty (in )?breathing|trouble breathing|(can'?t|cannot|unable to) breathe|short(ness)? of breath|breathless|gasping|struggling to breathe|hard to breathe|wheezing badly",
        "ta": r"மூச்சுத்திணறல்|மூச்சு விட சிரமம்|மூச்சு வாங்குகிறது|சுவாசிக்க சிரமம்|மூச்சு விட முடியவில்லை",
        "te": r"ఊపిరి ఆడక|శ్వాస తీసుకోవడంలో ఇబ్బంది|ఊపిరి తీసుకోలేక|ఊపిరి తీసుకోవడం కష్టం",
        "hi": r"सांस लेने में (तकलीफ|दिक्कत|कठिनाई)|साँस लेने में (तकलीफ|दिक्कत|कठिनाई)|सांस फूल|साँस फूल|दम घुट|सांस नहीं ले|साँस नहीं ले"}),
    "unconscious_or_seizure": ("emergency", {
        "en": r"unconscious|passed out|fainted|fainting|seizure|convulsion|\bfits\b|unresponsive|not responding|won'?t wake|can'?t wake",
        "ta": r"மயங்கி விழு|சுயநினைவு இழ|சுயநினைவு இல்ல|வலிப்பு|மயக்கம் அடைந்த|மயங்கிவிட்ட",
        "te": r"స్పృహ కోల్పో|స్పృహ తప్పి|మూర్ఛ|ఫిట్స్|కళ్లు తిరిగి పడిపో",
        "hi": r"बेहोश|दौरा पड़|मिर्गी|होश नहीं|मूर्छा|अचेत"}),
    "stroke_signs": ("emergency", {
        "en": r"face (is )?droop|drooping (of )?(the )?face|slurred speech|can'?t speak|cannot speak|sudden (weakness|numbness)|(weakness|numbness) (on|in) one side|one side of (my )?body|sudden loss of (vision|sight)|worst headache of my life",
        "ta": r"முகம் கோணல்|பேச்சு குளறு|பேச முடியவில்லை|ஒரு பக்க (கை|கால்|உடல்)|திடீர் பலவீனம்|திடீரென பார்வை",
        "te": r"ముఖం వంగ|మాట తడబడ|మాట్లాడలేక|ఒక వైపు (చేయి|కాలు|శరీరం)|హఠాత్తుగా బలహీన",
        "hi": r"चेहरा टेढ़ा|बोलने में दिक्कत|जुबान लड़खड़|ज़ुबान लड़खड़|एक तरफ (का )?(हाथ|पैर|शरीर)|अचानक कमजोरी|अचानक नजर"}),
    "severe_bleeding": ("emergency", {
        "en": r"vomit(ing|ed)? blood|blood (in|with) (my )?(vomit|stool|urine|sputum)|coughing (up )?blood|cough(ing)? blood|black (tarry )?stool|tarry stool|heavy bleeding|severe bleeding|bleeding (that )?(won'?t|will not|does not) stop|bleeding a lot",
        "ta": r"(இரத்த|ரத்த) வாந்தி|(இரத்தம்|ரத்தம்) கலந்த|இருமலில் (இரத்தம்|ரத்தம்)|மலத்தில் (இரத்தம்|ரத்தம்)|அதிக (இரத்த|ரத்த)ப்போக்கு|கருப்பு நிற மலம்|(இரத்தம்|ரத்தம்) நிற்கவில்லை",
        "te": r"రక్తం వాంతి|రక్తపు వాంతు|మలంలో రక్తం|దగ్గులో రక్తం|ఎక్కువ రక్తస్రావం|నల్లటి మలం|రక్తం ఆగడం లేదు",
        "hi": r"खून की उल्टी|उल्टी में खून|मल में खून|खांसी में खून|खाँसी में खून|खून बंद नहीं|ज्यादा खून|ज़्यादा खून|काला मल|खूनी दस्त|पेशाब में खून"}),
    "anaphylaxis": ("emergency", {
        "en": r"swelling of (the |my )?(face|lips|tongue|throat)|(face|lips|tongue|throat) (is |are )?swelling|throat (is )?closing|anaphyla|(face|lip|tongue) swollen",
        "ta": r"முகம் வீங்க|உதடு வீங்க|நாக்கு வீங்க|தொண்டை அடைப்பு|தொண்டை அடைக்கிறது",
        "te": r"ముఖం ఉబ్బ|పెదవులు ఉబ్బ|నాలుక వాపు|గొంతు మూసుకు|నాలుక ఉబ్బ",
        "hi": r"चेहरे पर सूजन|चेहरा सूज|होंठ सूज|जीभ सूज|गला बंद|गले में सूजन के साथ"}),
    "poisoning_overdose": ("emergency", {
        "en": r"poison|overdose|swallowed (bleach|pesticide|kerosene|acid|detergent)|drank (pesticide|acid|kerosene|bleach)|took too many (pills|tablets)",
        "ta": r"விஷம்|நஞ்சு|அதிக மாத்திரை|பூச்சி மருந்து",
        "te": r"విషం|పురుగుల మందు|ఎక్కువ మాత్రలు",
        "hi": r"जहर|ज़हर|ओवरडोज|कीटनाशक (पी|खा)|ज्यादा गोलियां|ज़्यादा गोलियाँ"}),
    "confusion": ("emergency", {
        "en": r"confus(ed|ion)|disoriented|not making sense|very drowsy|extremely drowsy|hard to stay awake",
        "ta": r"குழப்பமாக உள்ளது|நினைவு தடுமாற|தெளிவில்லாமல் பேசு|அதிக தூக்க நிலை",
        "te": r"గందరగోళంగా|అయోమయం|మతిభ్రమ|స్పృహ మందగ",
        "hi": r"भ्रमित|होश में नहीं|उलझन में हूँ|बहुत ज्यादा नींद|बहुत ज़्यादा नींद|दिमाग काम नहीं"}),
    "severe_abdominal_pain": ("emergency", {
        "en": r"(severe|unbearable|excruciating|worst) (abdominal|stomach|belly|tummy) pain|(abdominal|stomach|belly) pain (is )?(unbearable|severe)|rigid (abdomen|stomach)|hard (abdomen|belly)",
        "ta": r"(கடுமையான|தாங்க முடியாத) வயிற்று வலி|வயிறு கல் போல",
        "te": r"(తీవ్రమైన|భరించలేని) కడుపు నొప్పి|కడుపు రాయిలా",
        "hi": r"पेट में (तेज|बहुत|असहनीय) दर्द|असहनीय पेट दर्द|पेट (बहुत )?कड़ा"}),
    "suicidal_ideation": ("crisis", {
        "en": r"kill myself|suicid|want to die|end my life|end it all|self[- ]harm|hurt myself|better off dead",
        "ta": r"தற்கொலை|சாக வேண்டும்|உயிரை மாய்த்து|சாகலாம் போல|வாழ பிடிக்கவில்லை",
        "te": r"ఆత్మహత్య|చనిపోవాలని|చావాలని|బతకాలని లేదు",
        "hi": r"आत्महत्या|मरना चाहता|मरना चाहती|जान दे दू|जान दे दूँ|खुद को खत्म|जीने का मन नहीं"}),
}
_STIFF_NECK = {"en": r"stiff neck|neck stiffness", "ta": r"கழுத்து இறுக்கம்|கழுத்து விறைப்பு", "te": r"మెడ బిగుసు|మెడ నొప్పి మరియు జ్వరం", "hi": r"गर्दन अकड़|गर्दन में अकड़न"}
_FEVER_ANY = r"fever|temperature|காய்ச்சல்|జ్వరం|बुखार"
_NO_URINE = {"en": r"no urine|not (passed|passing) urine|haven'?t (passed|urinated)|not urinated", "ta": r"சிறுநீர் வரவில்லை|சிறுநீர் கழிக்கவில்லை", "te": r"మూత్రం రావడం లేదు|మూత్రం పోవడం లేదు", "hi": r"पेशाब नहीं आ|पेशाब नहीं हुआ"}
_CANT_KEEP_FLUIDS = {"en": r"(can'?t|cannot|unable to) (keep|hold) (down )?(any )?(fluids|water|liquids)|vomit(ing)? everything", "ta": r"தண்ணீர் கூட தங்கவில்லை|எதுவும் குடிக்க முடியவில்லை", "te": r"నీళ్లు కూడా తాగలేక|ఏమీ తాగలేకపోతున్న", "hi": r"पानी भी नहीं पच|कुछ भी पी नहीं पा|उल्टी में सब कुछ"}

CHRONIC_VULNERABLE = {
    "diabetes": r"diabet|sugar", "heart": r"heart|cardiac|coronary|bypass|stent", "kidney": r"kidney|renal|dialysis",
    "liver": r"liver|hepat|cirrho", "lung": r"asthma|copd|lung|tuberc|\btb\b", "cancer": r"cancer|chemo|tumou?r",
    "immune": r"hiv|immun|transplant|steroid", "pregnancy": r"pregnan",
}
INFECTION_LIKE = {"fever", "cough", "diarrhea", "vomiting", "sore throat", "cold", "breathlessness"}


@dataclass
class RiskAssessment:
    level: str                                   # "low" | "medium" | "high"
    category: str = "none"                       # "emergency" | "crisis" | "none"
    rules: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    ruleset: str = RULESET_VERSION
    complete: bool = True                        # False when key facts are still unknown

    def as_dict(self) -> dict:
        return {"level": self.level, "category": self.category, "rules": self.rules,
                "reasons": self.reasons, "ruleset": self.ruleset, "complete": self.complete}


def _search_all(patterns: dict[str, str], text: str) -> bool:
    return any(re.search(p, text, re.I) for p in patterns.values())


_NEGATED_PREFIX = re.compile(
    r"(?:\b(?:no|not|without|never|denies|denied)\b|\b(?:don'?t|do not|doesn'?t|does not|didn'?t|have not|haven'?t) (?:have|had|feel|get|got))\s*(?:any\s+|a\s+|the\s+)?(?:\w+\s+)?$")


def _match_unnegated(patterns: dict[str, str], t: str) -> bool:
    """True if any pattern matches and the match is not directly negated (English only:
    'no chest pain'). 'No relief, chest pain' or 'no fever but chest pain' stay positive.
    Indic-language negation is NOT parsed -- those matches are treated as positive (conservative)."""
    for lang, pat in patterns.items():
        for m in re.finditer(pat, t, re.I):
            prefix = t[max(0, m.start() - 30):m.start()]
            if lang == "en" and _NEGATED_PREFIX.search(prefix):
                continue
            return True
    return False


def detect_red_flags(text: str) -> tuple[list[str], str]:
    """Pure text screen, run on EVERY user message (also before any follow-up question)."""
    t = norm(text)
    hits, category = [], "none"
    for rid, (cat, pats) in HIGH_RULES.items():
        if _match_unnegated(pats, t):
            hits.append(rid)
            if cat == "crisis":
                category = "crisis"
            elif category != "crisis":
                category = "emergency"
    if _match_unnegated(_STIFF_NECK, t) and re.search(_FEVER_ANY, t):
        hits.append("stiff_neck_with_fever")
        category = category if category == "crisis" else "emergency"
    return hits, category


def assess(text: str, *, symptoms: list[str] | None = None, duration_days: float | None = None,
           severity: str | None = None, fever_c: float | None = None, worsening: bool = False,
           age_years: float | None = None, chronic_text: str = "", pregnant: bool = False,
           warning_screen: str | None = None) -> RiskAssessment:
    """Full assessment. `text` is the cumulative user text of the consultation."""
    symptoms = symptoms or []
    t = norm(text)
    rules: list[str] = []
    reasons: list[str] = []

    hits, category = detect_red_flags(text)
    if warning_screen == "yes":
        hits.append("warning_screen_positive")
        category = category if category != "none" else "emergency"
    if fever_c is not None and fever_c >= 40.0:
        hits.append("fever_ge_40c")
        category = category if category != "none" else "emergency"
    has_fever = "fever" in symptoms or bool(re.search(_FEVER_ANY, t))
    if has_fever and age_years is not None and age_years < 0.25:
        hits.append("infant_under_3_months_with_fever")
        category = category if category != "none" else "emergency"
    if pregnant and "severe_bleeding" in hits:
        hits.append("pregnancy_with_bleeding")
    if hits:
        return RiskAssessment("high", category, hits, [f"red-flag:{h}" for h in hits])

    # ------------------------------------------------------------ MEDIUM rules
    def add(rid: str, why: str):
        rules.append(rid)
        reasons.append(why)

    if has_fever and duration_days is not None and duration_days >= 3:
        add("fever_ge_3_days", "Fever lasting 3 days or more")
    if fever_c is not None and fever_c >= 39.0:
        add("fever_ge_39c", "High measured temperature (39 C / 102.2 F or above)")
    if "cough" in symptoms and duration_days is not None and duration_days >= 14:
        add("cough_ge_2_weeks", "Cough lasting 2 weeks or more")
    if "diarrhea" in symptoms and duration_days is not None and duration_days >= 2:
        add("diarrhea_ge_2_days", "Diarrhoea lasting 2 days or more")
    if "vomiting" in symptoms and duration_days is not None and duration_days >= 1:
        add("vomiting_ge_1_day", "Vomiting lasting a day or more")
    if duration_days is not None and duration_days >= 7:
        add("any_symptom_ge_7_days", "Symptoms lasting a week or more")
    if severity == "severe":
        add("severe_intensity", "Symptoms described as severe")
    if worsening:
        add("worsening", "Symptoms reported as worsening or not improving")
    if _search_all(_NO_URINE, t) or _search_all(_CANT_KEEP_FLUIDS, t):
        add("dehydration_signs", "Possible dehydration (not passing urine / unable to keep fluids down)")
    if age_years is not None:
        if age_years < 1:
            add("infant", "Symptoms in an infant under one year")
        elif age_years < 5 and has_fever:
            add("child_under_5_fever", "Fever in a child under 5 years")
        elif age_years >= 65 and (has_fever or any(s in INFECTION_LIKE for s in symptoms)):
            add("age_ge_65_infection_like", "Infection-like symptoms at age 65 or above")
    vuln = [k for k, p in CHRONIC_VULNERABLE.items() if re.search(p, (chronic_text or "").lower())]
    if pregnant and "pregnancy" not in vuln:
        vuln.append("pregnancy")
    if vuln and (has_fever or any(s in INFECTION_LIKE for s in symptoms)):
        add("vulnerable_condition_with_infection_like", "Infection-like symptoms together with a long-term condition or pregnancy")

    complete = bool(symptoms) and duration_days is not None
    if rules:
        return RiskAssessment("medium", "none", rules, reasons, complete=complete)
    return RiskAssessment("low", "none", [], ["No red flags or escalation criteria found in the information provided"], complete=complete)
