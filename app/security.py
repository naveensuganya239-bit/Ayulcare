"""Authentication helpers, CSRF protection, security headers, validation utilities."""
from __future__ import annotations

import hmac
import re
import secrets
from datetime import timedelta
from functools import wraps

from flask import g, jsonify, redirect, request, session, url_for

from .extensions import db
from .models import User, utcnow

EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[^@\s]{2,}$")


def api_error(message: str, status: int = 400, **extra):
    return jsonify({"error": message, **extra}), status


def current_user() -> User | None:
    if "user" not in g:
        uid = session.get("uid")
        g.user = db.session.get(User, uid) if uid else None
    return g.user


def login_user(user: User):
    session.clear()
    session["uid"] = user.id
    session["csrf"] = secrets.token_urlsafe(32)
    session.permanent = True
    g.user = user


def logout_user():
    session.clear()
    g.user = None


def csrf_token() -> str:
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(32)
    return session["csrf"]


def check_csrf():
    sent = request.headers.get("X-CSRF-Token", "")
    if not sent or not hmac.compare_digest(sent, session.get("csrf", "")):
        return api_error("Invalid or missing CSRF token. Please refresh the page.", 403)
    return None


def login_required_api(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        if not current_user():
            return api_error("Authentication required.", 401)
        return fn(*a, **kw)
    return wrapper


def login_required_page(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        if not current_user():
            return redirect(url_for("pages.login", next=request.path))
        return fn(*a, **kw)
    return wrapper


def consent_required_api(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        u = current_user()
        if not u:
            return api_error("Authentication required.", 401)
        if not u.consent_health_at:
            return api_error("Please give consent to process health information first.", 403, code="consent_required")
        return fn(*a, **kw)
    return wrapper


def researcher_required_api(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        u = current_user()
        if not u:
            return api_error("Authentication required.", 401)
        if u.role != "researcher":
            return api_error("Researcher access required.", 403)
        return fn(*a, **kw)
    return wrapper


def is_locked(user: User) -> bool:
    return bool(user.locked_until and user.locked_until > utcnow())


def register_failed_login(user: User):
    user.failed_logins = (user.failed_logins or 0) + 1
    if user.failed_logins >= 5:
        user.locked_until = utcnow() + timedelta(minutes=15)
        user.failed_logins = 0
    db.session.commit()


def validate_password(pw: str) -> str | None:
    if len(pw) < 10:
        return "Password must be at least 10 characters."
    if len(pw) > 128:
        return "Password is too long."
    if not (re.search(r"[A-Za-z]", pw) and re.search(r"\d", pw)):
        return "Password must contain letters and numbers."
    if pw.lower() in {"password123", "1234567890", "qwerty12345"}:
        return "Password is too common."
    return None


def clean_str(value, max_len: int, allow_empty: bool = True):
    if value is None:
        return None if allow_empty else ""
    s = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", str(value)).strip()
    return s[:max_len] if s else (None if allow_empty else "")


def float_in(value, lo: float, hi: float):
    if value in (None, ""):
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        raise ValueError("number expected")
    if not lo <= v <= hi:
        raise ValueError(f"value must be between {lo} and {hi}")
    return v


CSP = ("default-src 'self'; img-src 'self' data:; media-src 'self' blob:; "
       "style-src 'self' https://fonts.googleapis.com; style-src-attr 'unsafe-inline'; font-src 'self' https://fonts.gstatic.com; "
       "script-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'")


def init_security(app):
    @app.before_request
    def _csrf_guard():
        if request.method in ("POST", "PUT", "PATCH", "DELETE") and request.path.startswith("/api/"):
            return check_csrf()

    @app.after_request
    def _headers(resp):
        resp.headers.setdefault("Content-Security-Policy", CSP)
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        resp.headers.setdefault("Permissions-Policy", "camera=(), geolocation=(), microphone=(self)")
        if request.path.startswith("/api/"):
            resp.headers["Cache-Control"] = "no-store"
        return resp
