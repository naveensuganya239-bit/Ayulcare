"""General lifestyle EDUCATION from voluntarily provided profile data.

No personalised diet plans, no medication/treatment instructions, no conclusions drawn
from demographics. Each card states its basis. Thresholds are published public-health
guidance (WHO / sleep-medicine consensus) and should be re-verified before publication.
"""
from __future__ import annotations

from .privacy import age_years

WHO = "https://www.who.int/news-room/fact-sheets/detail/"


def bmi(height_cm, weight_kg):
    if not height_cm or not weight_kg or height_cm < 80:
        return None
    return round(weight_kg / ((height_cm / 100) ** 2), 1)


def build_cards(profile) -> dict:
    cards = []
    age = age_years(profile.date_of_birth) if profile else None
    conditions = bool(profile and profile.chronic_conditions)
    pregnant = bool(profile and profile.pregnant)

    def card(key, title, body, basis, link=None, note=None):
        cards.append({"key": key, "title": title, "body": body, "basis": basis, "link": link, "note": note})

    if profile and bmi(profile.height_cm, profile.weight_kg):
        b = bmi(profile.height_cm, profile.weight_kg)
        if age is not None and age < 19:
            body = f"Your BMI works out to {b}. For people under 19, BMI is interpreted on age- and sex-specific growth charts, so please ask a doctor or use WHO growth references."
        else:
            band = "below 18.5 (underweight range)" if b < 18.5 else "18.5-24.9 (WHO healthy range)" if b < 25 else "25-29.9 (WHO overweight range)" if b < 30 else "30 or above (WHO obesity range)"
            body = (f"Your BMI works out to {b}, which is {band}. BMI is a population screening tool, not a diagnosis; "
                    "WHO notes that for many Asian populations risk rises at lower BMI values (action points around 23 and 27.5).")
        card("bmi", "Body-mass index (BMI)", body, "WHO BMI classification", WHO.replace("fact-sheets/detail/", "health-topics/obesity"))
    if profile and profile.sleep_hours:
        h = profile.sleep_hours
        if age is not None and age < 18:
            body = f"You reported about {h:g} hours of sleep. Children and teenagers generally need more sleep than adults (roughly 8-10 hours for teenagers)."
        elif h < 7:
            body = f"You reported about {h:g} hours of sleep. Sleep-medicine consensus suggests most adults need 7 or more hours. Regular bed/wake times, less screen light at night and limiting late caffeine can help. If poor sleep is persistent, mention it to a doctor."
        elif h > 9:
            body = f"You reported about {h:g} hours of sleep. Needs vary, but if you regularly sleep this long and still feel tired, it is worth mentioning to a doctor."
        else:
            body = f"You reported about {h:g} hours of sleep, which is within the range commonly recommended for adults (7-9 hours). Keeping regular sleep times supports this."
        card("sleep", "Sleep", body, "Adult Sleep Duration Consensus (AASM/SRS) and general sleep-hygiene guidance")
    card("activity", "Physical activity",
         "WHO suggests adults aim for at least 150-300 minutes of moderate activity per week (for example brisk walking), and children and adolescents about 60 minutes a day. Start gradually.",
         "WHO physical activity fact sheet", WHO + "physical-activity",
         "If you have a long-term condition or are pregnant, ask your clinician what activity is suitable for you." if (conditions or pregnant) else None)
    pref = (profile.food_preference or "") if profile else ""
    diet = ("WHO healthy-diet guidance: at least 400 g of vegetables and fruit a day, less than 5 g of salt a day, and free sugars below 10% of energy intake. "
            "Prefer whole grains, pulses and nuts over refined and fried foods.")
    if pref == "vegetarian":
        diet += " On a vegetarian diet, a varied mix of pulses, dairy, nuts and seeds helps; ask a clinician whether vitamin B12 needs attention."
    card("diet", "Balanced eating", diet, "WHO healthy diet fact sheet", WHO + "healthy-diet",
         "This is general education, not a personal diet plan. With a long-term condition, follow your doctor's or dietitian's advice." if conditions else None)
    card("hydration", "Hydration",
         "Drink water regularly through the day; needs vary with heat, activity and health. Pale-yellow urine is a rough everyday sign of good hydration.",
         "General public-health guidance", None,
         "If you have heart or kidney disease, follow your doctor's advice on how much to drink." if conditions else None)
    if profile and profile.smoking == "yes":
        card("smoking", "Tobacco", "Tobacco use raises the risk of lung, heart and many other diseases, and quitting helps at any age. A doctor or a quit-line can offer support that improves your chances of success.",
             "WHO tobacco fact sheet", WHO + "tobacco")
    if profile and profile.alcohol == "yes":
        card("alcohol", "Alcohol", "WHO states that no level of alcohol consumption is completely safe for health; less is better. If you drink, consider cutting down, and talk to a doctor if you find that difficult.",
             "WHO alcohol fact sheet", WHO + "alcohol")
    if pregnant:
        card("pregnancy", "Pregnancy", "Diet, activity and any remedies during pregnancy should be discussed with your antenatal care provider.", "General safety principle")
    return {"cards": cards, "disclaimer": "General lifestyle education only - not medical advice, not a diet plan, and not a treatment recommendation."}
