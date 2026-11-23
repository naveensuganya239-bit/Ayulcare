import multiprocessing
import os

bind = f"0.0.0.0:{os.getenv('PORT', '8000')}"
# Models (embedder, Whisper) are memory heavy: keep workers few, use threads for concurrency.
workers = int(os.getenv("WEB_CONCURRENCY", min(2, multiprocessing.cpu_count())))
threads = int(os.getenv("GUNICORN_THREADS", 4))
timeout = 120          # first request may load models
graceful_timeout = 30
preload_app = False    # each worker loads its own FAISS index lazily
accesslog = "-"
errorlog = "-"
