"""Flask CLI: flask --app wsgi <command>"""
from __future__ import annotations

import json

import click
from flask import current_app
from werkzeug.security import generate_password_hash

from .extensions import db


def register_cli(app):
    @app.cli.command("init-db")
    def init_db():
        """Create database tables."""
        db.create_all()
        click.echo("Database ready.")

    @app.cli.command("build-index")
    @click.option("--force", is_flag=True, help="Rebuild even if a valid index exists.")
    def build_index(force):
        """Embed the CSV and persist the FAISS index (never modifies the CSV)."""
        svc = current_app.extensions["svc"]
        svc.ds = svc.ds or __import__("app.services.dataset", fromlist=["DatasetStore"]).DatasetStore(current_app.config["DATASET_PATH"])
        from .services.embeddings import get_embedder
        from .services.vectorstore import VectorStore
        emb = get_embedder(current_app.config["EMBEDDING_BACKEND"], current_app.config["EMBEDDING_MODEL"])
        store = VectorStore(current_app.config["INDEX_DIR"], emb, svc.ds.sha256)
        if force or not store.load():
            meta = store.build(svc.ds.df)
            click.echo(f"Built index: {meta['n_records']} records, model={meta['embedding_model']}, {meta['build_seconds']}s")
        else:
            click.echo("Existing index is valid; nothing to do (use --force to rebuild).")

    @app.cli.command("data-report")
    def data_report():
        """Write data/reports/data_quality.json describing the dataset (read-only)."""
        svc = current_app.extensions["svc"].ensure_ready()
        p = svc.ds.write_quality_report(current_app.config["REPORT_DIR"])
        click.echo(json.dumps({k: svc.ds.quality[k] for k in ("n_records", "n_header_columns", "risk_status_counts", "risk_final_distribution")}, indent=2))
        click.echo(f"Full report: {p}")

    @app.cli.command("check-integrity")
    def check_integrity():
        """Verify the CSV still matches its SHA-256 baseline."""
        svc = current_app.extensions["svc"].ensure_ready()
        click.echo(json.dumps(svc.ds.verify_integrity(), indent=2))

    @app.cli.command("calibrate-thresholds")
    def calibrate():
        """Print similarity distributions to help choose retrieval thresholds."""
        svc = current_app.extensions["svc"].ensure_ready()
        click.echo(json.dumps(svc.retriever.calibration_report(), indent=2))

    @app.cli.command("create-researcher")
    @click.argument("email")
    @click.password_option()
    def create_researcher(email, password):
        """Create (or promote) a researcher account for the evaluation dashboard."""
        from .models import Profile, User, utcnow
        from .security import validate_password
        err = validate_password(password)
        if err:
            raise click.ClickException(err)
        email = email.strip().lower()
        u = User.query.filter_by(email=email).first()
        if u:
            u.role = "researcher"
        else:
            u = User(email=email, password_hash=generate_password_hash(password), role="researcher",
                     consent_terms_at=utcnow(), consent_version=current_app.config["CONSENT_VERSION"])
            u.profile = Profile()
            db.session.add(u)
        db.session.commit()
        click.echo(f"Researcher ready: {email}")

    @app.cli.command("run-eval")
    @click.option("--testset", default="data/eval/retrieval_testset.csv", show_default=True)
    @click.option("--k", default="1,3,5,10", show_default=True)
    @click.option("--name", default=None, help="Report name suffix")
    def run_eval(testset, k, name):
        """Run the retrieval evaluation (problem-only vs symptom-RAG vs proposed)."""
        from .evaluation.runner import run_retrieval_eval
        svc = current_app.extensions["svc"].ensure_ready()
        ks = [int(x) for x in k.split(",")]
        out = run_retrieval_eval(svc, current_app.config, testset, ks, name)
        click.echo(json.dumps(out["summary"], indent=2))
        click.echo(f"Report written to: {out['path']}")

    @app.cli.command("eval-safety")
    def eval_safety():
        """Run the safety (red-flag) and language-detection test suites."""
        from .evaluation.safety_lang import run_language_eval, run_safety_eval
        out = {"safety": run_safety_eval(current_app.config), "language": run_language_eval(current_app.config)}
        click.echo(json.dumps({k: v["summary"] for k, v in out.items()}, indent=2))

    @app.cli.command("make-testset-template")
    @click.option("--n", default=150, show_default=True)
    def make_template(n):
        """Draft a stratified test-set TEMPLATE for expert annotation (not ground truth)."""
        from .evaluation.testset import write_template
        svc = current_app.extensions["svc"].ensure_ready()
        p = write_template(svc.ds, current_app.config["EVAL_DIR"], n)
        click.echo(f"Template written: {p}\nExperts must rewrite queries in natural patient language and verify relevant SNo values.")
