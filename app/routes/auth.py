from __future__ import annotations

from flask import Blueprint, jsonify, request, session
from werkzeug.security import check_password_hash, generate_password_hash

from ..extensions import db, limiter
from ..models import ConsentLog, Profile, User, utcnow
from ..security import (EMAIL_RE, api_error, csrf_token, current_user, is_locked, login_required_api, login_user,
                        logout_user, register_failed_login, validate_password)

bp = Blueprint("auth", __name__, url_prefix="/api")
_DUMMY_HASH = generate_password_hash("dummy-password-for-timing")


def user_json(u: User) -> dict:
    return {"id": u.id, "email": u.email, "role": u.role, "consent_health": bool(u.consent_health_at),
            "consent_ai_context": bool(u.consent_ai_context), "consent_research": bool(u.consent_research),
            "profile_completed": bool(u.profile and u.profile.completed)}


@bp.get("/csrf")
def csrf():
    return jsonify(csrf=csrf_token())


@bp.get("/auth/me")
def me():
    u = current_user()
    return jsonify(user=user_json(u) if u else None, csrf=csrf_token())


@bp.post("/auth/register")
@limiter.limit("8 per minute; 40 per hour")
def register():
    d = request.get_json(silent=True) or {}
    email = str(d.get("email", "")).strip().lower()
    pw = str(d.get("password", ""))
    if not EMAIL_RE.match(email) or len(email) > 254:
        return api_error("Please enter a valid email address.")
    err = validate_password(pw)
    if err:
        return api_error(err)
    if d.get("consent_terms") is not True:
        return api_error("You must accept the Terms and Privacy Notice to create an account.")
    if User.query.filter_by(email=email).first():
        return api_error("An account with this email already exists. Try logging in.", 409)
    from flask import current_app
    ver = current_app.config["CONSENT_VERSION"]
    u = User(email=email, password_hash=generate_password_hash(pw), consent_terms_at=utcnow(), consent_version=ver)
    u.profile = Profile()
    db.session.add(u)
    db.session.flush()
    db.session.add(ConsentLog(user_id=u.id, kind="terms_privacy", granted=True, version=ver))
    db.session.commit()
    login_user(u)
    return jsonify(user=user_json(u), csrf=csrf_token()), 201


@bp.post("/auth/login")
@limiter.limit("10 per minute; 60 per hour")
def login():
    d = request.get_json(silent=True) or {}
    email = str(d.get("email", "")).strip().lower()
    pw = str(d.get("password", ""))
    u = User.query.filter_by(email=email).first()
    if u and is_locked(u):
        return api_error("Too many failed attempts. Try again in 15 minutes.", 429)
    ok = check_password_hash(u.password_hash if u else _DUMMY_HASH, pw)
    if not (u and ok):
        if u:
            register_failed_login(u)
        return api_error("Incorrect email or password.", 401)
    u.failed_logins, u.last_login_at = 0, utcnow()
    db.session.commit()
    login_user(u)
    return jsonify(user=user_json(u), csrf=csrf_token())


@bp.post("/auth/logout")
def logout():
    logout_user()
    return jsonify(ok=True, csrf=csrf_token())


@bp.post("/auth/change-password")
@login_required_api
@limiter.limit("5 per minute")
def change_password():
    d = request.get_json(silent=True) or {}
    u = current_user()
    if not check_password_hash(u.password_hash, str(d.get("current_password", ""))):
        return api_error("Current password is incorrect.", 403)
    err = validate_password(str(d.get("new_password", "")))
    if err:
        return api_error(err)
    u.password_hash = generate_password_hash(str(d["new_password"]))
    db.session.commit()
    return jsonify(ok=True)
