# Ayurveda AI - multilingual, grounded Ayurvedic health-information assistant

Informational **research prototype** (IEEE paper project). It does not diagnose, does not replace a doctor, and does not claim any traditional remedy is effective.

**Stack:** Flask REST API - SQLite (dev) / PostgreSQL (cloud) - pandas - Sentence-Transformers (`intfloat/multilingual-e5-small`) - FAISS - Google Gemini (server-side only) - Whisper (faster-whisper) - browser Speech Synthesis - vanilla HTML/CSS/JS.

## Pipeline
```
user text/voice -> language detection -> symptom extraction (Gemini + lexicon)
 -> DETERMINISTIC red-flag screen (HIGH => static emergency reply, stop)
 -> follow-up questions for missing info (max 4, never repeated)
 -> deterministic risk (LOW/MEDIUM) -> FAISS symptom-aware retrieval over the CSV
 -> relevance threshold + safety filtering + remedy diversification
 -> (no match) trusted-domain web fallback, labelled external
 -> Gemini explanation (validated) or static template -> cards with author/book/record id
```

## Quick start (Windows PowerShell / VS Code)
```powershell
cd ayurveda-ai
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
# edit .env: SECRET_KEY, GEMINI_API_KEY; generate FIELD_ENCRYPTION_KEY with:
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

flask --app wsgi init-db
flask --app wsgi data-report          # data-quality report (CSV is never modified)
flask --app wsgi build-index          # embeds the 5,649 records once, persists FAISS index
flask --app wsgi calibrate-thresholds # choose retrieval thresholds for your embedding model
flask --app wsgi run --debug          # http://127.0.0.1:5000
```
Researcher dashboard account: `flask --app wsgi create-researcher you@example.com`.
Run tests: `pip install pytest; $env:APP_ENV="testing"; pytest -q`.

No internet / quick UI check: set `EMBEDDING_BACKEND=hash` (offline fallback, **never for reported results**).
`ffmpeg` is recommended for Whisper on some platforms (`winget install ffmpeg`).

## Dataset
Put your CSV at `DATASET_PATH` (default `data/original/Combined_All_3_CSV_Files.csv`, already included, read-only). See **docs/DATA_NOTES.md**: the uploaded file has 13 header columns (not 14) and 50 records keep their risk label in a blank-header column; this is handled by a per-record fallback rule and reported transparently.

## Docs
`docs/DATA_NOTES.md` - dataset handling - `docs/SAFETY.md` - risk rules and limits - `docs/EVALUATION.md` - reproducible experiments - `docs/DEPLOYMENT.md` - cloud.

## Layout
```
app/            Flask package (config, models, security, routes/, services/, evaluation/, templates/, static/)
data/original   source CSV + SHA256SUMS (read-only)       data/index   persisted FAISS index
data/eval       test-set template + README                 data/reports generated reports
tests/          pytest suite                                Dockerfile, docker-compose.yml, render.yaml, Procfile
```

## What still needs humans (honest checklist)
1. Clinician review of `app/services/risk.py` rules/thresholds and of all emergency/safety messages.
2. Native-speaker review of Tamil/Telugu/Hindi strings (`app/i18n_strings.py`, `symptoms.py`, `risk.py`).
3. Expert-verified retrieval test set (see docs/EVALUATION.md) before reporting any metric.
4. Calibrating retrieval thresholds with the real embedding model (defaults are placeholders).
5. Legal/ethics review (privacy notice, IRB) before real users.
