"""Flask application factory."""
from __future__ import annotations

import logging
import os
import sys

from flask import Flask, jsonify, render_template, request

from .config import get_config
from .extensions import db, limiter


def create_app(config_name: str | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=False)
    cfg = get_config(config_name)
    if cfg.__name__ == "ProductionConfig":
        cfg.validate()
    app.config.from_object(cfg)

    logging.basicConfig(level=logging.INFO, stream=sys.stdout,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    # Never log request bodies; werkzeug access log shows method/path/status only.
    os.makedirs(os.path.join(app.config["BASE_DIR"], "instance"), exist_ok=True)

    db.init_app(app)
    limiter.init_app(app)

    from .security import csrf_token, current_user, init_security
    init_security(app)

    from .services.consultation import ConsultationEngine
    from .services.container import Services
    svc = Services(app.config)
    app.extensions["svc"] = svc
    app.extensions["engine"] = ConsultationEngine(svc, app.config)

    from .routes import auth, chat_api, pages, research, user_api
    for bp in (pages.bp, auth.bp, user_api.bp, chat_api.bp, research.bp):
        app.register_blueprint(bp)

    @app.context_processor
    def inject():
        return {"csrf_token": csrf_token(), "me": current_user(), "app_env": app.config["ENV"]}

    @app.errorhandler(404)
    def _404(e):
        if request.path.startswith("/api/"):
            return jsonify(error="Not found"), 404
        return render_template("error.html", code=404, message="That page could not be found."), 404

    @app.errorhandler(413)
    def _413(e):
        return jsonify(error="Upload too large."), 413

    @app.errorhandler(429)
    def _429(e):
        return jsonify(error="Too many requests. Please slow down and try again shortly."), 429

    @app.errorhandler(500)
    def _500(e):
        app.logger.exception("Unhandled error")  # stack trace only; no user content
        if request.path.startswith("/api/"):
            return jsonify(error="Something went wrong on our side."), 500
        return render_template("error.html", code=500, message="Something went wrong on our side."), 500

    with app.app_context():
        from . import models  # noqa: F401
        db.create_all()

    from .cli import register_cli
    register_cli(app)
    return app
