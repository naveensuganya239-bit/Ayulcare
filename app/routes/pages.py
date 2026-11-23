from __future__ import annotations

from flask import Blueprint, abort, current_app, jsonify, redirect, render_template, url_for

from ..security import current_user, login_required_page

bp = Blueprint("pages", __name__)


@bp.get("/")
def landing():
    return render_template("landing.html")


@bp.get("/register")
def register():
    return redirect(url_for("pages.dashboard")) if current_user() else render_template("register.html")


@bp.get("/login")
def login():
    return redirect(url_for("pages.dashboard")) if current_user() else render_template("login.html")


@bp.get("/setup")
@login_required_page
def setup():
    return render_template("setup.html")


@bp.get("/dashboard")
@login_required_page
def dashboard():
    return render_template("dashboard.html")


@bp.get("/chat")
@bp.get("/chat/<int:cid>")
@login_required_page
def chat(cid=None):
    return render_template("chat.html", cid=cid)


@bp.get("/history")
@login_required_page
def history():
    return render_template("history.html")


@bp.get("/lifestyle")
@login_required_page
def lifestyle():
    return render_template("lifestyle.html")


@bp.get("/feedback")
@login_required_page
def feedback():
    return render_template("feedback.html")


@bp.get("/settings")
@login_required_page
def settings():
    return render_template("settings.html")


@bp.get("/research")
@login_required_page
def research():
    if current_user().role != "researcher":
        abort(404)
    return render_template("research.html")


@bp.get("/privacy")
def privacy():
    return render_template("privacy.html")


@bp.get("/healthz")
def healthz():
    return jsonify(status="ok", **{k: v for k, v in current_app.extensions["svc"].status().items() if k in ("ready", "gemini", "web_search")})
