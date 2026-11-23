# Deployment

## Environment checklist
`APP_ENV=production`, `SECRET_KEY` (>=32 random chars), `FIELD_ENCRYPTION_KEY` (Fernet), `DATABASE_URL` (PostgreSQL), `SESSION_COOKIE_SECURE=true`, `RATELIMIT_STORAGE_URI=redis://...`, `GEMINI_API_KEY`, optional `GOOGLE_CSE_*`. **Back up `FIELD_ENCRYPTION_KEY`: losing it makes encrypted profile/chat data unreadable.**

## Docker (recommended)
```bash
docker compose up --build
```
The FAISS index lives in the `faiss_index` volume and is reused across restarts; it rebuilds only if the dataset or model changes.

## Render / Railway / Fly.io
Use the Dockerfile. Mount a persistent disk at `/srv/data/index`. Memory: the multilingual-e5-small model plus Whisper `small` needs roughly 2 GB RAM; use `WHISPER_MODEL=base` or run STT on a separate worker on small free tiers.

## Free-tier notes
Gemini and Google Programmable Search have free quotas; the app degrades gracefully (template responses, no web fallback) when keys are absent or quotas are exhausted.

## Operations
* `flask --app wsgi create-researcher you@example.com` creates the evaluation-dashboard account.
* Use HTTPS only (HSTS at the proxy). Terminate TLS at the platform load balancer.
* Logs contain request lines and stack traces only, never message text, Gemini prompts or profile data.
* Before going public: clinician review of risk rules, native-speaker review of translations, legal review of the privacy notice, ethics/IRB approval for user studies.
