# Safety design

## Principles
1. Emergency risk is decided by **deterministic rules** (`app/services/risk.py`), never by Gemini.
2. Red-flag screening runs on **every** user message, before any follow-up question. HIGH produces a static, pre-written message (EN/TA/TE/HI), no questions, no remedies.
3. Dataset risk labels are not clinical triage rules.
4. Gemini only explains retrieved records. Its output is validated: unknown record ids, or any number (dose, quantity) not present in the records or the user's message, causes the narrative to be rejected and replaced by a static template.
5. Remedy text shown to users is the **verbatim dataset text** (English/Tamil). Telugu/Hindi translations are optional AI output, labelled, and dropped if numbers differ from the source.

## Rule set status: DRAFT
`RULESET_VERSION = 0.1-draft-awaiting-clinical-review`. The red-flag categories (chest pain, breathing difficulty, loss of consciousness/seizure, stroke signs, serious bleeding, anaphylaxis, poisoning, confusion, severe abdominal pain, stiff neck with fever, suicidal ideation, fever >= 40 C, fever in infants < 3 months) and the MEDIUM rules (fever >= 3 days, cough >= 2 weeks, etc.) are conservative and widely published categories, **but they have not been validated by clinicians.** Before real-world use: have a qualified physician review every rule and threshold, and every Tamil/Telugu/Hindi phrase list and message.

## Known limitations
* English negation ("no chest pain") is handled; Indic-language negation is not (conservative: matches escalate).
* Keyword matching cannot understand every phrasing or misspelling. It is a safety net, not a diagnostic tool. Extend `HIGH_RULES` using real anonymised logs.
* Romanised Tamil/Hindi/Telugu (e.g. "kaichal") is detected only weakly; red-flag detection does not cover romanised text.
* Emergency numbers (112, 108, Tele-MANAS 14416) are India-specific and must be verified/adapted for the deployment region.
* The Tele-MANAS and ambulance numbers should be re-verified before launch.

## Medium-risk and monitoring behaviour
Medium risk shows at most two records once, then refuses to repeat remedies. Follow-ups are scheduled (24 h medium, 48 h low); "worse" or "new symptoms" escalates to medical care; "no change" advises seeing a doctor and does not encourage continuing a remedy.
