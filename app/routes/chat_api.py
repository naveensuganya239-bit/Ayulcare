from __future__ import annotations

from datetime import timedelta

from flask import Blueprint, Response, current_app, jsonify, request

from ..extensions import db, limiter
from ..i18n_strings import t
from ..models import Consultation, Feedback, FollowUp, utcnow
from ..security import api_error, clean_str, consent_required_api, current_user
from ..services.speech import SUPPORTED_AUDIO

bp = Blueprint("chat_api", __name__, url_prefix="/api")


def _own_consult(cid: int):
    c = db.session.get(Consultation, cid)
    return c if c and c.user_id == current_user().id else None


def _msg_json(m):
    return {"id": m.id, "role": m.role, "text": m.content, "payload": m.payload if m.role == "assistant" else None,
            "mode": m.input_mode, "at": m.created_at.isoformat()}


@bp.post("/chat/start")
@consent_required_api
@limiter.limit("30 per hour")
def start():
    c = current_app.extensions["engine"].start(current_user())
    return jsonify(id=c.id), 201


@bp.post("/chat/<int:cid>/message")
@consent_required_api
@limiter.limit("40 per minute; 400 per hour")
def message(cid):
    c = _own_consult(cid)
    if not c:
        return api_error("Consultation not found.", 404)
    d = request.get_json(silent=True) or {}
    text = clean_str(d.get("text"), current_app.config["MAX_MESSAGE_CHARS"] + 1, allow_empty=False)
    if not text:
        return api_error("Please type or speak a message.")
    if len(text) > current_app.config["MAX_MESSAGE_CHARS"]:
        return api_error(f"Message too long (max {current_app.config['MAX_MESSAGE_CHARS']} characters).")
    lang = d.get("lang") if d.get("lang") in ("auto", "en", "ta", "te", "hi") else "auto"
    mode = "voice" if d.get("input_mode") == "voice" else "text"
    replies = current_app.extensions["engine"].handle(current_user(), c, text, lang, mode)
    return jsonify(replies=replies, language=c.language, risk_level=c.risk_level,
                   consultation={"id": c.id, "title": c.title, "status": c.status})


@bp.get("/chat/<int:cid>")
@consent_required_api
def get_chat(cid):
    c = _own_consult(cid)
    if not c:
        return api_error("Consultation not found.", 404)
    return jsonify(consultation={"id": c.id, "title": c.title, "status": c.status, "risk_level": c.risk_level,
                                 "language": c.language, "started_at": c.started_at.isoformat()},
                   messages=[_msg_json(m) for m in c.messages],
                   greeting=t("greeting", c.language or "en"))


@bp.get("/consultations")
@consent_required_api
def list_consultations():
    rows = Consultation.query.filter_by(user_id=current_user().id).order_by(Consultation.updated_at.desc()).limit(200).all()
    return jsonify(items=[{"id": c.id, "title": c.title, "risk": c.risk_level, "status": c.status, "language": c.language,
                           "started": c.started_at.isoformat(), "updated": c.updated_at.isoformat(), "messages": len(c.messages)} for c in rows])


@bp.delete("/consultations/<int:cid>")
@consent_required_api
def delete_consultation(cid):
    c = _own_consult(cid)
    if not c:
        return api_error("Consultation not found.", 404)
    from ..models import RetrievalLog
    RetrievalLog.query.filter_by(consultation_id=cid).update({RetrievalLog.consultation_id: None})
    Feedback.query.filter_by(consultation_id=cid).update({Feedback.consultation_id: None})
    FollowUp.query.filter_by(consultation_id=cid).delete()
    db.session.delete(c)
    db.session.commit()
    return jsonify(ok=True)


# ----------------------------------------------------------------- voice
@bp.get("/voice/status")
@consent_required_api
def voice_status():
    svc = current_app.extensions["svc"]
    return jsonify(available=svc.stt.check(), model=svc.stt.model_name)


@bp.post("/voice/transcribe")
@consent_required_api
@limiter.limit("12 per minute; 120 per hour")
def transcribe():
    svc = current_app.extensions["svc"]
    if not svc.stt.check():
        return api_error("Voice input is not available on this server. Please type your message.", 503, code="stt_unavailable")
    f = request.files.get("audio")
    if not f:
        return api_error("No audio received.")
    mime = (f.mimetype or "").split(";")[0].lower()
    if mime not in SUPPORTED_AUDIO:
        return api_error("Unsupported audio format.", 415)
    data = f.read()
    if len(data) < 800:
        return api_error("The recording was too short.")
    suffix = {"audio/webm": ".webm", "video/webm": ".webm", "audio/ogg": ".ogg", "audio/mp4": ".m4a", "audio/x-m4a": ".m4a",
              "audio/m4a": ".m4a", "audio/wav": ".wav", "audio/x-wav": ".wav", "audio/mpeg": ".mp3", "audio/aac": ".aac"}.get(mime, ".webm")
    lang = request.form.get("lang")
    try:
        out = svc.stt.transcribe(data, suffix, None if lang in (None, "", "auto") else lang)
    except Exception as exc:
        current_app.logger.exception("Transcription failed")
        err_str = str(exc)
        # Detect the faster-whisper / PyAV incompatibility specifically
        if "metadata_errors" in err_str or ("unexpected keyword argument" in err_str and "open" in err_str):
            return api_error(
                "Voice engine error (PyAV incompatibility). Using browser voice instead.",
                503, code="stt_engine_error"
            )
        return api_error("Could not transcribe that recording. Please try again or type your message.", 500,
                         code="stt_error")
    if not out["text"]:
        return api_error("I could not hear any speech. Please try again.", 422, code="stt_no_speech")
    return jsonify(**out)


@bp.post("/voice/synthesize")
@consent_required_api
@limiter.limit("12 per minute; 120 per hour")
def synthesize_voice():
    d = request.get_json(silent=True) or {}
    text = clean_str(d.get("text"), 6001, allow_empty=False)
    if not text:
        return api_error("Speech text is required.")
    if len(text) > 6000:
        return api_error("Speech text is too long.")
    language = d.get("language")
    if language not in ("ta", "te", "hi"):
        return api_error("On-device speech is available for Tamil, Telugu, and Hindi only.")

    try:
        audio = current_app.extensions["svc"].tts.synthesize(text, language)
    except Exception:
        current_app.logger.exception("On-device speech synthesis failed")
        return api_error(
            "Could not prepare the on-device voice. Please retry or use text.",
            503,
            code="tts_unavailable",
        )

    return Response(
        audio,
        mimetype="audio/wav",
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


# ------------------------------------------------------------- follow-ups
@bp.get("/followups")
@consent_required_api
def followups():
    rows = FollowUp.query.filter_by(user_id=current_user().id, status="pending").order_by(FollowUp.due_at).all()
    now = utcnow()
    out = []
    for f in rows:
        c = db.session.get(Consultation, f.consultation_id)
        out.append({"id": f.id, "consultation_id": f.consultation_id, "title": c.title if c else "Consultation",
                    "risk": c.risk_level if c else None, "due_at": f.due_at.isoformat(), "due": f.due_at <= now,
                    "language": c.language if c else "en"})
    return jsonify(items=out)


@bp.post("/feedback")
@consent_required_api
@limiter.limit("30 per hour")
def feedback():
    u = current_user()
    d = request.get_json(silent=True) or {}
    outcome = d.get("outcome")
    if outcome not in (None, "improved", "partial", "no_change", "worse"):
        return api_error("Invalid outcome.")
    used = d.get("used_recommendation")
    if used not in (None, "yes", "no", "partly"):
        return api_error("Invalid value for 'used recommendation'.")
    rating = d.get("helpfulness")
    if rating is not None:
        try:
            rating = int(rating)
        except (TypeError, ValueError):
            return api_error("Rating must be 1-5.")
        if not 1 <= rating <= 5:
            return api_error("Rating must be 1-5.")
    if outcome is None and rating is None:
        return api_error("Please give a rating or report how you are feeling.")
    c = _own_consult(int(d["consultation_id"])) if d.get("consultation_id") else None
    if d.get("consultation_id") and not c:
        return api_error("Consultation not found.", 404)
    fu = None
    if d.get("followup_id"):
        fu = db.session.get(FollowUp, int(d["followup_id"]))
        if not fu or fu.user_id != u.id:
            return api_error("Follow-up not found.", 404)
    fb = Feedback(user_id=u.id, consultation_id=c.id if c else None, followup_id=fu.id if fu else None, outcome=outcome,
                  new_symptoms=bool(d.get("new_symptoms")), used_recommendation=used, helpfulness=rating,
                  language=c.language if c else None, risk_level=c.risk_level if c else None,
                  comment=clean_str(d.get("comment"), 500))
    db.session.add(fb)
    advice, escalate = None, False
    lang = (c.language if c else "en") or "en"
    if fu and outcome:
        fu.status = "done"
    if outcome == "worse" or fb.new_symptoms:
        advice, escalate = t("worse_escalation", lang), True
        if c:
            c.risk_level, c.status = "medium" if c.risk_level == "low" else c.risk_level, "escalated"
    elif outcome == "no_change":
        advice = t("unchanged_advice", lang)
        if fu and c:  # one more check-in, but never open-ended remedy encouragement
            db.session.add(FollowUp(consultation_id=c.id, user_id=u.id, due_at=utcnow() + timedelta(hours=24)))
    elif outcome in ("improved", "partial"):
        advice = t("improved_advice", lang)
    db.session.commit()
    return jsonify(ok=True, advice=advice, escalate=escalate)
