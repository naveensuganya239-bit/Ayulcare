"""Researcher-only evaluation dashboard API (role == 'researcher')."""
from __future__ import annotations

import csv
import io
import json
from collections import Counter

from flask import Blueprint, Response, current_app, jsonify
from sqlalchemy import func

from ..extensions import db
from ..models import Consultation, Feedback, RetrievalLog, User
from ..security import researcher_required_api

bp = Blueprint("research", __name__, url_prefix="/api/research")


def _pct(n, d):
    return round(100.0 * n / d, 1) if d else None


@bp.get("/summary")
@researcher_required_api
def summary():
    # Only feedback from users who opted in to research use is aggregated.
    fb_q = Feedback.query.join(User, User.id == Feedback.user_id).filter(User.consent_research.is_(True))
    fb = fb_q.all()
    outcomes = Counter(f.outcome for f in fb if f.outcome)
    n_out = sum(outcomes.values())
    ratings = [f.helpfulness for f in fb if f.helpfulness]
    used = Counter(f.used_recommendation for f in fb if f.used_recommendation)
    logs = RetrievalLog.query
    n_logs = logs.count()
    prop = logs.filter(RetrievalLog.mode == "proposed")
    n_prop = prop.count()
    scores = []
    for (s,) in prop.with_entities(RetrievalLog.top_scores_json).limit(5000):
        arr = json.loads(s or "[]")
        if arr:
            scores.append(arr[0])
    return jsonify(
        consultations=Consultation.query.count(),
        users=User.query.count(),
        feedback_total=Feedback.query.count(),
        feedback_in_research_scope=len(fb),
        outcomes={"n": n_out, "improved": outcomes["improved"], "partial": outcomes["partial"], "no_change": outcomes["no_change"], "worse": outcomes["worse"],
                  "improved_pct": _pct(outcomes["improved"], n_out), "partial_pct": _pct(outcomes["partial"], n_out),
                  "no_change_pct": _pct(outcomes["no_change"], n_out), "worse_pct": _pct(outcomes["worse"], n_out)},
        satisfaction={"n": len(ratings), "mean": round(sum(ratings) / len(ratings), 2) if ratings else None,
                      "distribution": {str(k): ratings.count(k) for k in range(1, 6)}},
        used_recommendation=dict(used),
        retrieval={"logged_retrievals": n_logs, "proposed_mode": n_prop,
                   "no_match_pct": _pct(prop.filter(RetrievalLog.no_match.is_(True)).count(), n_prop),
                   "web_fallback_pct": _pct(logs.filter(RetrievalLog.web_fallback.is_(True)).count(), n_logs),
                   "mean_top_rank_score": round(sum(scores) / len(scores), 4) if scores else None,
                   "explanations_rejected_by_guard": logs.filter(RetrievalLog.explanation_rejected.is_(True)).count(),
                   "by_language": dict(db.session.query(RetrievalLog.language, func.count()).group_by(RetrievalLog.language).all()),
                   "by_risk": dict(db.session.query(RetrievalLog.risk_level, func.count()).group_by(RetrievalLog.risk_level).all())},
        caveat="User-reported outcomes are self-reports. They are NOT medical accuracy, clinical validation or proof of treatment effectiveness.",
        system=current_app.extensions["svc"].status(),
    )


@bp.get("/eval-reports")
@researcher_required_api
def eval_reports():
    d = current_app.config["REPORT_DIR"]
    out = []
    for p in sorted(d.glob("eval_*.json"), reverse=True)[:10]:
        try:
            out.append({"file": p.name, "report": json.loads(p.read_text(encoding="utf-8"))})
        except Exception:
            continue
    quality = d / "data_quality.json"
    return jsonify(reports=out, data_quality=json.loads(quality.read_text(encoding="utf-8")) if quality.exists() else None)


def _csv_response(rows, header, name):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(header)
    w.writerows(rows)
    return Response(buf.getvalue(), mimetype="text/csv", headers={"Content-Disposition": f"attachment; filename={name}"})


@bp.get("/export/feedback.csv")
@researcher_required_api
def export_feedback():
    rows = (Feedback.query.join(User, User.id == Feedback.user_id).filter(User.consent_research.is_(True)).all())
    return _csv_response([[f.id, f.created_at.date().isoformat(), f.language, f.risk_level, f.outcome, int(bool(f.new_symptoms)),
                           f.used_recommendation, f.helpfulness] for f in rows],
                         ["id", "date", "language", "risk_level", "outcome", "new_symptoms", "used_recommendation", "helpfulness"], "feedback_anonymised.csv")


@bp.get("/export/retrieval.csv")
@researcher_required_api
def export_retrieval():
    rows = RetrievalLog.query.order_by(RetrievalLog.id).limit(50000).all()
    return _csv_response([[r.id, r.created_at.date().isoformat(), r.language, r.mode, r.symptoms_json, r.top_ids_json, r.top_scores_json,
                           r.n_candidates, int(bool(r.no_match)), int(bool(r.web_fallback)), r.risk_level] for r in rows],
                         ["id", "date", "language", "mode", "symptoms", "top_record_ids", "top_scores", "n_candidates", "no_match", "web_fallback", "risk_level"],
                         "retrieval_log.csv")
