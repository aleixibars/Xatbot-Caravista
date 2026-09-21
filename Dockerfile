# Reviu tax RAG chatbot — Render Web Service image (see render.yaml, ADR-0002).
FROM python:3.12-slim

WORKDIR /app

# Install dependencies first for layer caching.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Render sets $PORT; default to 10000 for local `docker run`.
ENV PORT=10000
EXPOSE 10000

# Single worker: per-session history lives in the process (ADR-0002).
# exec → gunicorn becomes PID 1 so Render's SIGTERM triggers a graceful shutdown.
# --timeout 120: an embed + Qdrant search + chat completion can exceed the 30s default.
CMD exec gunicorn --workers 1 --threads 8 --timeout 120 --bind 0.0.0.0:$PORT app.web:app
