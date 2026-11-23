"""Application configuration. All secrets come from environment variables."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def _float(name: str, default: float | None = None):
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _db_url() -> str:
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        return f"sqlite:///{BASE_DIR / 'instance' / 'app.db'}"
    if url.startswith("postgres://"):  # Heroku-style
        url = url.replace("postgres://", "postgresql://", 1)
    if url.startswith("sqlite:///") and not url.startswith("sqlite:////"):
        rel = url.replace("sqlite:///", "", 1)
        url = f"sqlite:///{(BASE_DIR / rel).resolve()}"
    return url


def _path(name: str, default: str) -> Path:
    p = Path(os.getenv(name, default))
    return p if p.is_absolute() else (BASE_DIR / p).resolve()


class Config:
    ENV = os.getenv("APP_ENV", "development")
    DEBUG = False
    TESTING = False
    BASE_DIR = BASE_DIR

    SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-insecure-key")
    FIELD_ENCRYPTION_KEY = os.getenv("FIELD_ENCRYPTION_KEY", "").strip()

    SQLALCHEMY_DATABASE_URI = _db_url()
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _bool("SESSION_COOKIE_SECURE", False)
    PERMANENT_SESSION_LIFETIME = 60 * 60 * 12
    MAX_CONTENT_LENGTH = 12 * 1024 * 1024  # audio uploads

    RATELIMIT_STORAGE_URI = os.getenv("RATELIMIT_STORAGE_URI", "memory://")
    RATELIMIT_HEADERS_ENABLED = True

    # Dataset / index (the dataset is READ ONLY)
    DATASET_PATH = _path("DATASET_PATH", "data/original/Combined_All_3_CSV_Files.csv")
    INDEX_DIR = _path("INDEX_DIR", "data/index")
    REPORT_DIR = BASE_DIR / "data" / "reports"
    EVAL_DIR = BASE_DIR / "data" / "eval"

    # Embeddings
    EMBEDDING_BACKEND = os.getenv("EMBEDDING_BACKEND", "sentence-transformers")
    EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "intfloat/multilingual-e5-small")
    RETRIEVAL_MIN_SYMPTOM_SIM = _float("RETRIEVAL_MIN_SYMPTOM_SIM")
    RETRIEVAL_MIN_FULL_SIM = _float("RETRIEVAL_MIN_FULL_SIM")
    # Ranking weights. These are engineering hyper-parameters to be tuned on a
    # development split -- they are NOT clinically derived.
    RANK_WEIGHTS = {"symptom": 0.50, "coverage": 0.20, "full": 0.22, "problem": 0.08}
    RETRIEVAL_CANDIDATES = 200
    MAX_PROBLEM_GROUPS = 4
    MAX_REMEDIES_PER_GROUP = 3
    GROUP_SCORE_DELTA = 0.05
    EXCLUDE_DATASET_HIGH = True  # dataset "High" labels are never shown as home remedies

    # Gemini
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
    # gemini-1.5-flash is free-tier on Google AI Studio; gemini-2.5-flash requires billing
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
    GEMINI_TIMEOUT = 30

    # Web search fallback
    GOOGLE_CSE_API_KEY = os.getenv("GOOGLE_CSE_API_KEY", "").strip()
    GOOGLE_CSE_CX = os.getenv("GOOGLE_CSE_CX", "").strip()

    # Whisper
    WHISPER_MODEL = os.getenv("WHISPER_MODEL", "small")
    WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cpu")
    WHISPER_COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "int8")

    # Consultation behaviour
    MAX_FOLLOWUP_QUESTIONS = 3   # reduced from 4 for faster remedy delivery
    MAX_MESSAGE_CHARS = 1500
    FOLLOWUP_HOURS_LOW = int(os.getenv("FOLLOWUP_HOURS_LOW", "48"))
    FOLLOWUP_HOURS_MEDIUM = int(os.getenv("FOLLOWUP_HOURS_MEDIUM", "24"))
    CONSENT_VERSION = "2026-11-v1"


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    SESSION_COOKIE_SECURE = True

    @classmethod
    def validate(cls):
        if cls.SECRET_KEY == "dev-only-insecure-key" or len(cls.SECRET_KEY) < 32:
            raise RuntimeError("SECRET_KEY must be set to a random string of >= 32 chars in production.")
        if not cls.FIELD_ENCRYPTION_KEY:
            raise RuntimeError("FIELD_ENCRYPTION_KEY must be set in production.")


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_ENGINE_OPTIONS = {}
    RATELIMIT_ENABLED = False
    EMBEDDING_BACKEND = "hash"
    GEMINI_API_KEY = ""
    GOOGLE_CSE_API_KEY = ""
    SESSION_COOKIE_SECURE = False


def get_config(name: str | None = None):
    name = (name or os.getenv("APP_ENV", "development")).lower()
    return {"production": ProductionConfig, "testing": TestingConfig}.get(name, DevelopmentConfig)
