"""Database models. Sensitive profile fields are encrypted at rest (Fernet)."""
from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime, timezone

from cryptography.fernet import Fernet, InvalidToken
from flask import current_app
from sqlalchemy.types import Text, TypeDecorator

from .extensions import db


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _fernet() -> Fernet:
    key = current_app.config.get("FIELD_ENCRYPTION_KEY")
    if not key:  # development convenience only (production config refuses to start without a key)
        digest = hashlib.sha256(("dev-fernet:" + current_app.config["SECRET_KEY"]).encode()).digest()
        key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


class EncryptedText(TypeDecorator):
    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return None if value in (None, "") else _fernet().encrypt(value.encode("utf-8")).decode("ascii")

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        try:
            return _fernet().decrypt(value.encode("ascii")).decode("utf-8")
        except InvalidToken:
            return None


class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(254), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), default="user", nullable=False)  # user | researcher
    created_at = db.Column(db.DateTime, default=utcnow)
    last_login_at = db.Column(db.DateTime)
    failed_logins = db.Column(db.Integer, default=0)
    locked_until = db.Column(db.DateTime)
    consent_terms_at = db.Column(db.DateTime)
    consent_health_at = db.Column(db.DateTime)       # explicit consent to process health information
    consent_version = db.Column(db.String(30))
    consent_ai_context = db.Column(db.Boolean, default=False)  # share de-identified profile context with Gemini
    consent_research = db.Column(db.Boolean, default=False)    # include feedback in research statistics
    profile = db.relationship("Profile", uselist=False, backref="user", cascade="all, delete-orphan")
    consultations = db.relationship("Consultation", backref="user", cascade="all, delete-orphan")


class Profile(db.Model):
    __tablename__ = "profiles"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    name = db.Column(EncryptedText)
    date_of_birth = db.Column(db.Date)
    gender = db.Column(db.String(30))
    height_cm = db.Column(db.Float)
    weight_kg = db.Column(db.Float)
    chronic_conditions = db.Column(EncryptedText)
    acute_problems = db.Column(EncryptedText)
    alcohol = db.Column(db.String(20))
    smoking = db.Column(db.String(20))
    city = db.Column(db.String(80))
    area = db.Column(db.String(80))
    contact_number = db.Column(EncryptedText)
    contact_consent = db.Column(db.Boolean, default=False)
    menstrual_info = db.Column(EncryptedText)
    pregnant = db.Column(db.Boolean)
    sleep_hours = db.Column(db.Float)
    food_preference = db.Column(db.String(30))
    preferred_language = db.Column(db.String(5), default="auto")
    completed = db.Column(db.Boolean, default=False)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)


class Consultation(db.Model):
    __tablename__ = "consultations"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = db.Column(db.String(120), default="New consultation")
    language = db.Column(db.String(5), default="en")
    status = db.Column(db.String(20), default="open")       # open | assessed | escalated
    risk_level = db.Column(db.String(10))
    state_json = db.Column(EncryptedText)
    started_at = db.Column(db.DateTime, default=utcnow)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)
    messages = db.relationship("Message", backref="consultation", cascade="all, delete-orphan", order_by="Message.id")

    @property
    def state(self) -> dict:
        return json.loads(self.state_json) if self.state_json else {}

    @state.setter
    def state(self, value: dict):
        self.state_json = json.dumps(value, ensure_ascii=False)


class Message(db.Model):
    __tablename__ = "messages"
    id = db.Column(db.Integer, primary_key=True)
    consultation_id = db.Column(db.Integer, db.ForeignKey("consultations.id", ondelete="CASCADE"), nullable=False, index=True)
    role = db.Column(db.String(12), nullable=False)  # user | assistant
    content = db.Column(EncryptedText)
    payload_json = db.Column(EncryptedText)
    input_mode = db.Column(db.String(10))            # text | voice
    created_at = db.Column(db.DateTime, default=utcnow)

    @property
    def payload(self):
        return json.loads(self.payload_json) if self.payload_json else None


class FollowUp(db.Model):
    __tablename__ = "followups"
    id = db.Column(db.Integer, primary_key=True)
    consultation_id = db.Column(db.Integer, db.ForeignKey("consultations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    due_at = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(12), default="pending")  # pending | done
    created_at = db.Column(db.DateTime, default=utcnow)


class Feedback(db.Model):
    """Stored separately from the dataset. Deleted with the account."""
    __tablename__ = "feedback"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    consultation_id = db.Column(db.Integer, db.ForeignKey("consultations.id", ondelete="SET NULL"))
    followup_id = db.Column(db.Integer, db.ForeignKey("followups.id", ondelete="SET NULL"))
    outcome = db.Column(db.String(12))               # improved | partial | no_change | worse
    new_symptoms = db.Column(db.Boolean, default=False)
    used_recommendation = db.Column(db.String(8))    # yes | no | partly
    helpfulness = db.Column(db.Integer)              # 1-5
    language = db.Column(db.String(5))
    risk_level = db.Column(db.String(10))
    comment = db.Column(EncryptedText)
    created_at = db.Column(db.DateTime, default=utcnow)


class RetrievalLog(db.Model):
    """Research log. Holds NO user id and NO raw text: only extracted English symptom terms,
    record ids and scores. consultation_id is nulled when the consultation is deleted."""
    __tablename__ = "retrieval_logs"
    id = db.Column(db.Integer, primary_key=True)
    consultation_id = db.Column(db.Integer, db.ForeignKey("consultations.id", ondelete="SET NULL"))
    created_at = db.Column(db.DateTime, default=utcnow)
    language = db.Column(db.String(5))
    mode = db.Column(db.String(20))
    symptoms_json = db.Column(db.Text)
    top_ids_json = db.Column(db.Text)
    top_scores_json = db.Column(db.Text)
    dropped_json = db.Column(db.Text)
    n_candidates = db.Column(db.Integer)
    no_match = db.Column(db.Boolean)
    web_fallback = db.Column(db.Boolean, default=False)
    risk_level = db.Column(db.String(10))
    gemini_used = db.Column(db.Boolean, default=False)
    explanation_rejected = db.Column(db.Boolean, default=False)


class ConsentLog(db.Model):
    __tablename__ = "consent_logs"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    kind = db.Column(db.String(30), nullable=False)
    granted = db.Column(db.Boolean, nullable=False)
    version = db.Column(db.String(30))
    created_at = db.Column(db.DateTime, default=utcnow)
