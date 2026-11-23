"""Consultation orchestrator: conversation state machine + RAG pipeline.

User message
  -> language detection -> symptom extraction (Gemini if available + lexicon)
  -> DETERMINISTIC red-flag screen (before anything else)      [HIGH -> static emergency reply]
  -> missing-information check -> at most N targeted follow-up questions
  -> deterministic risk assessment (LOW / MEDIUM)
  -> FAISS symptom-aware retrieval + relevance/safety filtering
  -> (no match) controlled trusted-web fallback
  -> Gemini explanation of retrieved records (validated) or static template
  -> structured payload for the UI.
"""
from __future__ import annotations

import json
import re
from datetime import timedelta

from ..extensions import db
from ..i18n_strings import QUICK, QUICK_CANON, t
from ..models import Consultation, FollowUp, Message, RetrievalLog, utcnow
from .gemini import numbers_preserved, validate_explanation
from .language import resolve_reply_language
from .privacy import age_years, ai_safe_context, scrub
from .retrieval import Query, profile_condition_keys
from .risk import assess, detect_red_flags
from .symptoms import LEXICON, Extraction, extract_rule_based

MAX_TEXTS = 14


def new_state() -> dict:
    return {"v": 1, "lang": None, "slots": {"symptoms": [], "duration_days": None, "duration_text": None, "severity": None,
                                            "fever_c": None, "worsening": False, "other_subject": False,
                                            "patient_age_years": None, "warning_screen": None, "problem_hint": None},
            "asked": [], "pending": None, "rounds": 0, "texts": [], "stage": "collect",
            "shown_ids": [], "assessments": 0, "followup_created": False}


def symptom_label(canon: str, lang: str) -> str:
    forms = LEXICON.get(canon, {}).get(lang)
    return forms[0] if forms and lang != "en" else canon


class ConsultationEngine:
    def __init__(self, services, cfg):
        self.svc, self.cfg = services, cfg

    # ============================================================ public API
    def start(self, user) -> Consultation:
        c = Consultation(user_id=user.id, language="en")
        c.state = new_state()
        db.session.add(c)
        db.session.commit()
        return c

    def handle(self, user, consult: Consultation, text: str, manual_lang: str | None = None,
               input_mode: str = "text") -> list[dict]:
        self.svc.ensure_ready()
        st = consult.state or new_state()
        profile = user.profile
        prof_lang = profile.preferred_language if profile and profile.preferred_language not in (None, "auto") else None
        lang, det = resolve_reply_language(text, manual_lang if manual_lang not in (None, "auto") else None, st.get("lang"), prof_lang)
        st["lang"] = lang
        consult.language = lang

        db.session.add(Message(consultation_id=consult.id, role="user", content=text, input_mode=input_mode,
                               payload_json=json.dumps({"lang": lang, "detected": det.lang, "confidence": det.confidence,
                                                        "mixed": det.mixed}, ensure_ascii=False)))
        st["texts"] = (st.get("texts", []) + [text])[-MAX_TEXTS:]
        ext = self._extract(text, st, profile)
        self._apply_extraction(st, ext, text)

        replies = self._respond(user, consult, st, ext, text, lang)

        for r in replies:
            db.session.add(Message(consultation_id=consult.id, role="assistant", content=r["text"],
                                   payload_json=json.dumps(r.get("payload"), ensure_ascii=False) if r.get("payload") else None))
        if not consult.title or consult.title == "New consultation":
            syms = st["slots"]["symptoms"][:3]
            if syms:
                consult.title = ", ".join(s.capitalize() for s in syms)[:100]
        consult.state = st
        db.session.commit()
        return replies

    # ============================================================ extraction
    def _extract(self, text: str, st: dict, profile) -> Extraction:
        ext = extract_rule_based(text)
        if self.svc.gemini.enabled:
            names = [profile.name] if profile and profile.name else []
            known = ", ".join(st["slots"]["symptoms"])
            g = self.svc.gemini.extract(scrub(text, names), known)
            if g:
                ext.method = "gemini+lexicon"
                for s in g["symptoms"]:
                    if s not in ext.symptoms and s not in g["negated"]:
                        ext.symptoms.append(s)
                ext.negated = sorted(set(ext.negated) | set(g["negated"]))
                ext.symptoms = [s for s in ext.symptoms if s not in ext.negated]
                ext.duration_days = ext.duration_days if ext.duration_days is not None else g["duration_days"]
                ext.severity = ext.severity or g["severity"]
                ext.fever_c = ext.fever_c if ext.fever_c is not None else g["fever_c"]
                ext.worsening = ext.worsening or g["worsening"]
                ext.other_subject = ext.other_subject or g["other_subject"]
                ext.patient_age_years = ext.patient_age_years if ext.patient_age_years is not None else g["patient_age_years"]
                st["slots"]["problem_hint"] = g.get("problem_hint") or st["slots"].get("problem_hint")
        return ext

    def _apply_extraction(self, st: dict, ext: Extraction, text: str) -> None:
        sl = st["slots"]
        for s in ext.symptoms:
            if s not in sl["symptoms"]:
                sl["symptoms"].append(s)
        sl["symptoms"] = [s for s in sl["symptoms"] if s not in ext.negated][:12]
        if ext.duration_days is not None:
            sl["duration_days"], sl["duration_text"] = ext.duration_days, ext.duration_text
        if ext.severity:
            sl["severity"] = ext.severity
        if ext.fever_c is not None:
            sl["fever_c"] = ext.fever_c
        sl["worsening"] = sl["worsening"] or ext.worsening
        if ext.other_subject:
            sl["other_subject"] = True
        if ext.patient_age_years is not None and (sl["other_subject"] or st.get("pending") == "patient_age"):
            sl["patient_age_years"] = ext.patient_age_years
        pend = st.get("pending")
        if pend == "patient_age" and sl["patient_age_years"] is None:
            m = re.fullmatch(r"\s*(\d{1,3}(?:\.\d)?)\s*(?:years?|yrs?|வயது|ఏళ్ళు|साल)?\s*", text.lower())
            if m:
                sl["patient_age_years"] = float(m.group(1))
        if pend == "warning":
            if ext.yes_no in ("yes", "no"):
                sl["warning_screen"] = ext.yes_no

    # ============================================================== respond
    def _respond(self, user, consult, st, ext, text, lang) -> list[dict]:
        sl, profile = st["slots"], user.profile
        for_self = not sl["other_subject"]
        age = age_years(profile.date_of_birth) if (for_self and profile) else sl["patient_age_years"]
        chronic = (profile.chronic_conditions or "") if (for_self and profile) else ""
        pregnant = bool(for_self and profile and profile.pregnant)
        cum = "\n".join(st["texts"])

        risk = assess(cum, symptoms=sl["symptoms"], duration_days=sl["duration_days"], severity=sl["severity"],
                      fever_c=sl["fever_c"], worsening=sl["worsening"], age_years=age, chronic_text=chronic,
                      pregnant=pregnant, warning_screen=sl["warning_screen"])
        consult.risk_level = risk.level

        # ---- HIGH: immediate, static, no questions, no remedies ------------
        if risk.level == "high":
            st["stage"], consult.status, st["pending"] = "escalated", "escalated", None
            key = "crisis" if risk.category == "crisis" else "emergency"
            body = t(key, lang) + "\n\n" + t("high_followup", lang)
            return [{"text": body, "payload": {"type": "emergency", "category": risk.category, "risk": risk.as_dict(),
                                               "text": t(key, lang), "extra": t("high_followup", lang),
                                               "disclaimer": t("disclaimer", lang)}}]

        # ---- already assessed earlier in this consultation -------------------
        if st["stage"] == "assessed":
            changed = bool(ext.symptoms and set(ext.symptoms) - set(st.get("assessed_symptoms", []))) or ext.worsening
            if not changed:
                msg = t("greeting", lang) if False else t("unchanged_advice", lang)
                return [{"text": msg, "payload": {"type": "note", "risk": risk.as_dict(), "text": msg}}]
            return [self._assessment(user, consult, st, risk, lang, text, repeat=True)]

        # ---- missing information -> follow-up (bounded) --------------------
        q = self._next_question(st, lang)
        if q:
            return [q]

        st["pending"] = None
        return [self._assessment(user, consult, st, risk, lang, text, repeat=False)]

    # ----------------------------------------------------------- follow-ups
    def _next_question(self, st: dict, lang: str) -> dict | None:
        sl, asked = st["slots"], st["asked"]
        if st["rounds"] >= self.cfg["MAX_FOLLOWUP_QUESTIONS"]:
            return None

        def ask(key, qtext, quick_kind=None):
            asked.append(key)
            st["rounds"] += 1
            st["pending"] = key
            qr = []
            if quick_kind:
                qr = [{"label": l, "value": v} for l, v in zip(QUICK[quick_kind][lang], QUICK_CANON[quick_kind])]
            return {"text": qtext, "payload": {"type": "followup", "key": key, "text": qtext, "quick_replies": qr}}

        if sl["other_subject"] and sl["patient_age_years"] is None and "patient_age" not in asked:
            return ask("patient_age", t("ask_patient_age", lang))
        if not sl["symptoms"] and "describe" not in asked:
            return ask("describe", t("ask_describe", lang))
        if sl["duration_days"] is None and "duration" not in asked:
            return ask("duration", t("ask_duration", lang), "duration")
        if sl["warning_screen"] is None and "warning" not in asked:
            return ask("warning", t("ask_warning", lang), "yesno")
        syms = set(sl["symptoms"])
        if "specific" not in asked:
            key = ("ask_cough_type" if "cough" in syms else "ask_fever_measured" if ("fever" in syms and sl["fever_c"] is None)
                   else "ask_digestive" if syms & {"vomiting", "diarrhea"} else None)
            if key:
                return ask("specific", t(key, lang))
            if self.svc.gemini.enabled and syms:
                gq = self.svc.gemini.clarifying_question(sorted(syms), lang, [])
                if gq:
                    return ask("specific", gq)
        if sl["severity"] is None and "severity" not in asked:
            return ask("severity", t("ask_severity", lang), "severity")
        return None

    # ----------------------------------------------------------- assessment
    def _assessment(self, user, consult, st, risk, lang, text, repeat: bool) -> dict:
        sl, profile = st["slots"], user.profile
        st["stage"], consult.status = "assessed", "assessed"
        st["assessed_symptoms"] = list(sl["symptoms"])
        st["assessments"] += 1
        notice = t("medium_notice" if risk.level == "medium" else "low_notice", lang)
        gaps = []
        if sl["duration_days"] is None:
            gaps.append("duration")
        if sl["warning_screen"] is None:
            gaps.append("warning-sign screen")
        if sl["severity"] is None:
            gaps.append("severity")

        # medium risk: remedies shown once, never repeated
        if risk.level == "medium" and st["shown_ids"] and repeat:
            msg = t("medium_repeat", lang)
            return {"text": msg, "payload": {"type": "assessment", "risk": risk.as_dict(), "notice": msg, "remedies": [],
                                             "external": None, "no_match": False, "gaps": [], "disclaimer": t("disclaimer", lang)}}

        for_self = not sl["other_subject"]
        age = age_years(profile.date_of_birth) if (for_self and profile) else sl["patient_age_years"]
        conditions = profile_condition_keys((profile.chronic_conditions or "") if (for_self and profile) else "", age,
                                            bool(for_self and profile and profile.pregnant))
        cum = " ".join(st["texts"])
        query = Query(symptoms=list(sl["symptoms"]), text=cum[-600:], problem_hint=sl.get("problem_hint"), lang=lang, conditions=conditions)
        res = self.svc.retriever.search(query, "proposed", k=10)
        items = [i for i in res.items if i["record_id"] not in st["shown_ids"]]
        if risk.level == "medium":
            items = items[:2]
        self._log(consult, lang, query, res, risk.level, web=False)

        remedies = self._cards(items, lang)
        external = None
        explanation = None
        if remedies:
            st["shown_ids"] = list(dict.fromkeys(st["shown_ids"] + [r["record_id"] for r in remedies]))
            explanation = self._explain(user, remedies, risk, sl, lang, notice, cum)
        else:
            external = self._web_fallback(sl, lang, consult, res, risk.level)

        no_match = not remedies and not external
        followup_hours = None
        if not st["followup_created"]:
            followup_hours = self.cfg["FOLLOWUP_HOURS_MEDIUM"] if risk.level == "medium" else self.cfg["FOLLOWUP_HOURS_LOW"]
            db.session.add(FollowUp(consultation_id=consult.id, user_id=user.id, due_at=utcnow() + timedelta(hours=followup_hours)))
            st["followup_created"] = True

        parts = [notice]
        if explanation and explanation.get("summary"):
            parts.append(explanation["summary"])
        if no_match:
            parts += [t("no_match", lang), t("no_match_advice", lang)]
        if gaps:
            parts.append(t("info_gap_note", lang))
        payload = {
            "type": "assessment", "risk": risk.as_dict(), "notice": notice,
            "narrative": (explanation or {}).get("summary"), "care_note": (explanation or {}).get("care_note"),
            "remedies": remedies, "external": external, "no_match": no_match,
            "no_match_text": (t("no_match", lang) + " " + t("no_match_advice", lang)) if no_match else None,
            "gaps": gaps, "gap_text": t("info_gap_note", lang) if gaps else None,
            "followup_text": t("followup_scheduled", lang, hours=followup_hours) if followup_hours else None,
            "retrieval_note": ("Ranking uses text similarity to book records; it is not medical confidence."
                               if remedies else None),
            "disclaimer": t("disclaimer", lang),
        }
        return {"text": "\n\n".join(parts), "payload": payload}

    # --------------------------------------------------------------- helpers
    def _cards(self, items: list[dict], lang: str) -> list[dict]:
        ds, cards = self.svc.ds, []
        for n, it in enumerate(items, 1):
            rec = ds.get(it["record_id"])
            pub = ds.public(rec)
            card = {**pub, "ref": f"R{n}", "matched_symptoms": it["matched_symptoms"],
                    "matched_labels": [symptom_label(s, lang) for s in it["matched_symptoms"]],
                    "rank_score": it["score"], "precautions_in_text": it.get("precautions_in_text", []),
                    "translation": None, "translation_note": None}
            if lang in ("te", "hi") and self.svc.gemini.enabled:
                tr = self.svc.gemini.translate_remedy(pub["remedy_en"], lang)
                if tr and numbers_preserved(pub["remedy_en"], tr):
                    card["translation"], card["translation_note"] = tr, "AI translation - verify against the original text"
            cards.append(card)
        return cards

    def _explain(self, user, remedies, risk, sl, lang, notice, user_text):
        if not self.svc.gemini.enabled:
            # Graceful fallback: build a simple summary from retrieved records without Gemini
            return self._fallback_summary(remedies, lang)
        ctx = ai_safe_context(user.profile, bool(user.consent_ai_context)) if not sl["other_subject"] else {}
        raw = self.svc.gemini.explain(remedies, risk.level, sl["symptoms"], lang, notice, ctx)
        rec_text = " ".join(f"{r['remedy_en']} {r['problem_en']} {r['symptom_en']}" for r in remedies)
        ok = validate_explanation(raw, {r["ref"] for r in remedies}, rec_text, user_text)
        self._last_explanation_rejected = raw is not None and ok is None
        # If Gemini returned something but it was rejected by validation, use fallback
        if ok is None and raw is not None:
            return self._fallback_summary(remedies, lang)
        return ok

    def _fallback_summary(self, remedies: list[dict], lang: str) -> dict | None:
        """Build a plain-text summary from retrieved records when Gemini is unavailable."""
        if not remedies:
            return None
        problems = list(dict.fromkeys(r["problem_en"] for r in remedies))
        prob_str = " and ".join(problems[:2])
        refs = ", ".join(r["ref"] for r in remedies)
        # Pull the first concrete remedy text to make the summary specific
        first_remedy = remedies[0]["remedy_en"] if remedies else ""
        summary = (
            f"The Ayurvedic books contain records for {prob_str}. "
            f"For example, [{remedies[0]['ref']}] describes: \"{first_remedy[:120]}{'…' if len(first_remedy) > 120 else ''}\" "
            f"See all {len(remedies)} remedy card(s) below ({refs}) for the full documented preparations."
        )
        care_note = (
            "If symptoms worsen, persist beyond a few days, or are severe, "
            "consult a qualified doctor or AYUSH practitioner promptly."
        )
        why_matched = [
            {
                "id": r["ref"],
                "reason": (
                    f"Matched symptom(s): {', '.join(r.get('matched_symptoms', []) or [r['symptom_en']][:1])} "
                    f"→ {r['problem_en']}"
                ),
            }
            for r in remedies
        ]
        return {"summary": summary, "why_matched": why_matched, "care_note": care_note}

    def _web_fallback(self, sl, lang, consult, res, risk_level):
        if not (self.svc.web.enabled and sl["symptoms"]):
            return None
        results = self.svc.web.search(self.svc.web.build_query(sl["symptoms"]))
        if not results:
            return None
        summary = self.svc.gemini.summarise_external(results, lang, sl["symptoms"]) if self.svc.gemini.enabled else None
        db.session.add(RetrievalLog(consultation_id=consult.id, language=lang, mode="web_fallback",
                                    symptoms_json=json.dumps(sl["symptoms"]), top_ids_json="[]", top_scores_json="[]",
                                    n_candidates=0, no_match=False, web_fallback=True, risk_level=risk_level))
        return {"label": t("external_label", lang), "summary": summary, "results": results}

    def _log(self, consult, lang, query, res, risk_level, web):
        db.session.add(RetrievalLog(
            consultation_id=consult.id, language=lang, mode=res.mode, symptoms_json=json.dumps(query.symptoms, ensure_ascii=False),
            top_ids_json=json.dumps(res.ids), top_scores_json=json.dumps([i["score"] for i in res.items]),
            dropped_json=json.dumps(res.dropped[:30]), n_candidates=res.n_candidates, no_match=res.no_match,
            web_fallback=web, risk_level=risk_level, gemini_used=self.svc.gemini.enabled,
            explanation_rejected=bool(getattr(self, "_last_explanation_rejected", False))))
