from __future__ import annotations

import json
import re
from datetime import date

from flask import Blueprint, current_app, jsonify, request
from werkzeug.security import check_password_hash

from ..extensions import db, limiter
from ..models import ConsentLog, Consultation, Feedback, Message, Profile, User, utcnow
from ..security import (api_error, clean_str, consent_required_api, current_user, float_in, login_required_api,
                        logout_user)
from ..services.lifestyle import build_cards, bmi

bp = Blueprint("user_api", __name__, url_prefix="/api")

GENDERS = {"female", "male", "other", "prefer_not"}
YNP = {"yes", "no", "prefer_not"}
FOODS = {"vegetarian", "non_vegetarian", "eggetarian", "vegan", "other"}
LANGS = {"auto", "en", "ta", "te", "hi"}


def profile_json(p: Profile) -> dict:
    return {
        "name": p.name, "date_of_birth": p.date_of_birth.isoformat() if p.date_of_birth else None, "gender": p.gender,
        "height_cm": p.height_cm, "weight_kg": p.weight_kg, "bmi": bmi(p.height_cm, p.weight_kg),
        "chronic_conditions": p.chronic_conditions, "acute_problems": p.acute_problems, "alcohol": p.alcohol,
        "smoking": p.smoking, "city": p.city, "area": p.area, "contact_number": p.contact_number,
        "contact_consent": bool(p.contact_consent), "menstrual_info": p.menstrual_info, "pregnant": p.pregnant,
        "sleep_hours": p.sleep_hours, "food_preference": p.food_preference,
        "preferred_language": p.preferred_language or "auto", "completed": bool(p.completed),
    }


@bp.get("/profile")
@login_required_api
def get_profile():
    u = current_user()
    return jsonify(profile=profile_json(u.profile), consents={
        "health": bool(u.consent_health_at), "ai_context": bool(u.consent_ai_context),
        "research": bool(u.consent_research), "version": u.consent_version,
        "current_version": current_app.config["CONSENT_VERSION"]}, email=u.email)


@bp.put("/profile")
@login_required_api
@limiter.limit("30 per minute")
def put_profile():
    u = current_user()
    d = request.get_json(silent=True) or {}
    p = u.profile or Profile(user_id=u.id)
    try:
        if "name" in d:
            p.name = clean_str(d["name"], 80)
        if "date_of_birth" in d:
            v = d["date_of_birth"]
            if v:
                dob = date.fromisoformat(str(v))
                if not (date(1900, 1, 1) <= dob <= date.today()):
                    raise ValueError("date of birth out of range")
                p.date_of_birth = dob
            else:
                p.date_of_birth = None
        if "gender" in d:
            if d["gender"] not in (None, "") and d["gender"] not in GENDERS:
                raise ValueError("invalid gender")
            p.gender = d["gender"] or None
        if "height_cm" in d:
            p.height_cm = float_in(d["height_cm"], 40, 260)
        if "weight_kg" in d:
            p.weight_kg = float_in(d["weight_kg"], 1, 500)
        if "sleep_hours" in d:
            p.sleep_hours = float_in(d["sleep_hours"], 0, 24)
        for f in ("chronic_conditions", "acute_problems"):
            if f in d:
                setattr(p, f, clean_str(d[f], 600))
        if "menstrual_info" in d:
            p.menstrual_info = clean_str(d["menstrual_info"], 300)
        if "pregnant" in d:
            if d["pregnant"] not in (True, False, None):
                raise ValueError("invalid pregnancy value")
            p.pregnant = d["pregnant"]
        for f in ("alcohol", "smoking"):
            if f in d:
                if d[f] not in (None, "") and d[f] not in YNP:
                    raise ValueError(f"invalid {f}")
                setattr(p, f, d[f] or None)
        if "food_preference" in d:
            if d["food_preference"] not in (None, "") and d["food_preference"] not in FOODS:
                raise ValueError("invalid food preference")
            p.food_preference = d["food_preference"] or None
        if "city" in d:
            p.city = clean_str(d["city"], 80)
        if "area" in d:
            p.area = clean_str(d["area"], 80)
        if "preferred_language" in d:
            if d["preferred_language"] not in LANGS:
                raise ValueError("invalid language")
            p.preferred_language = d["preferred_language"]
        if "contact_consent" in d:
            p.contact_consent = bool(d["contact_consent"])
        if "contact_number" in d:
            num = clean_str(d["contact_number"], 20)
            if num and not re.fullmatch(r"\+?[\d\s-]{7,18}", num):
                raise ValueError("invalid contact number")
            if num and not (d.get("contact_consent", p.contact_consent)):
                raise ValueError("Please consent to storing a contact number, or leave it empty.")
            p.contact_number = num
        if not p.contact_consent:
            p.contact_number = None
        if d.get("completed") is True:
            p.completed = True
    except ValueError as exc:
        return api_error(f"Invalid input: {exc}")
    if p.id is None:
        db.session.add(p)
    db.session.commit()
    return jsonify(profile=profile_json(p))


@bp.post("/profile/consents")
@login_required_api
def set_consents():
    u = current_user()
    d = request.get_json(silent=True) or {}
    ver = current_app.config["CONSENT_VERSION"]

    def log(kind, granted):
        db.session.add(ConsentLog(user_id=u.id, kind=kind, granted=granted, version=ver))

    if "health" in d:
        if d["health"] and not u.consent_health_at:
            u.consent_health_at = utcnow()
            log("health_processing", True)
        elif not d["health"] and u.consent_health_at:
            u.consent_health_at = None
            log("health_processing", False)
    for key, col in (("ai_context", "consent_ai_context"), ("research", "consent_research")):
        if key in d and bool(d[key]) != bool(getattr(u, col)):
            setattr(u, col, bool(d[key]))
            log(key, bool(d[key]))
    u.consent_version = ver
    db.session.commit()
    return jsonify(consents={"health": bool(u.consent_health_at), "ai_context": bool(u.consent_ai_context),
                             "research": bool(u.consent_research)})


@bp.get("/lifestyle")
@consent_required_api
def lifestyle():
    return jsonify(build_cards(current_user().profile))


@bp.get("/dashboard")
@login_required_api
def dashboard():
    u = current_user()
    from ..models import FollowUp
    cons = Consultation.query.filter_by(user_id=u.id).order_by(Consultation.updated_at.desc()).limit(3).all()
    due = FollowUp.query.filter_by(user_id=u.id, status="pending").filter(FollowUp.due_at <= utcnow()).count()
    upcoming = FollowUp.query.filter_by(user_id=u.id, status="pending").filter(FollowUp.due_at > utcnow()).count()
    return jsonify(
        name=(u.profile.name.split()[0] if u.profile and u.profile.name else None),
        total=Consultation.query.filter_by(user_id=u.id).count(), due_followups=due, upcoming_followups=upcoming,
        recent=[{"id": c.id, "title": c.title, "risk": c.risk_level, "status": c.status, "updated": c.updated_at.isoformat()} for c in cons],
        profile_completed=bool(u.profile and u.profile.completed), consent_health=bool(u.consent_health_at))


@bp.get("/account/export")
@login_required_api
@limiter.limit("5 per hour")
def export_account():
    u = current_user()
    out = {"email": u.email, "created_at": u.created_at.isoformat(), "profile": profile_json(u.profile),
           "consents": {"health": bool(u.consent_health_at), "ai_context": bool(u.consent_ai_context), "research": bool(u.consent_research)},
           "consultations": [], "feedback": []}
    for c in u.consultations:
        out["consultations"].append({"id": c.id, "title": c.title, "started_at": c.started_at.isoformat(), "risk_level": c.risk_level,
                                     "messages": [{"role": m.role, "content": m.content, "at": m.created_at.isoformat()} for m in c.messages]})
    for f in Feedback.query.filter_by(user_id=u.id).all():
        out["feedback"].append({"consultation_id": f.consultation_id, "outcome": f.outcome, "helpfulness": f.helpfulness,
                                "used_recommendation": f.used_recommendation, "at": f.created_at.isoformat()})
    resp = jsonify(out)
    resp.headers["Content-Disposition"] = "attachment; filename=my-ayurveda-ai-data.json"
    return resp


@bp.delete("/account")
@login_required_api
@limiter.limit("3 per hour")
def delete_account():
    """Deletes the user and ALL associated data (profile, consultations, messages,
    follow-ups, feedback, consent log). Anonymous retrieval logs hold no user link and no
    raw text; their consultation reference is set to NULL."""
    u = current_user()
    d = request.get_json(silent=True) or {}
    if not check_password_hash(u.password_hash, str(d.get("password", ""))):
        return api_error("Password is incorrect.", 403)
    uid = u.id
    from ..models import FollowUp, RetrievalLog
    cids = [c.id for c in Consultation.query.filter_by(user_id=uid).all()]
    if cids:
        RetrievalLog.query.filter(RetrievalLog.consultation_id.in_(cids)).update({RetrievalLog.consultation_id: None}, synchronize_session=False)
    Feedback.query.filter_by(user_id=uid).delete(synchronize_session=False)
    FollowUp.query.filter_by(user_id=uid).delete(synchronize_session=False)
    ConsentLog.query.filter_by(user_id=uid).delete(synchronize_session=False)
    db.session.flush()
    for c in Consultation.query.filter_by(user_id=uid).all():
        db.session.delete(c)
    db.session.flush()
    db.session.delete(db.session.get(User, uid))
    db.session.commit()
    logout_user()
    return jsonify(ok=True)
