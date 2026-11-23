FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /srv
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg libgomp1 && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
# Pre-download the embedding model so the first request is fast (needs internet at build time)
ARG EMBEDDING_MODEL=intfloat/multilingual-e5-small
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('${EMBEDDING_MODEL}')" || true
RUN useradd -m app && chown -R app /srv
USER app
ENV APP_ENV=production PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "flask --app wsgi init-db && flask --app wsgi build-index && gunicorn -c gunicorn.conf.py wsgi:app"]
