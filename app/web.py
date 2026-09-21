"""Flask routes — thin, no business logic (see CODING_STANDARDS.md)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from flask import Flask, jsonify, request, send_from_directory
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from app import db, rag
from app.whatsapp import whatsapp_bp

# Per-session history, in-process only (see ADR-0002). Single gunicorn worker.
_history: dict[str, list[dict]] = {}

# Keep the last N messages per session.
_HISTORY_CAP: int = 20

# Build/seed the SQLite structured-data file (ADR-0003). Idempotent — only
# creates missing tables and seeds empty ones, so a container restart is safe.
db.init_db()

app = Flask(__name__, static_folder="static")

# WhatsApp channel (Meta Cloud API, issue #47) — GET/POST /webhook.
app.register_blueprint(whatsapp_bp)

# Per-IP rate limit on the open (no-login) chat endpoint — each call costs money
# (see ADR-0002). In-memory storage is fine for the single-worker PoC deploy.
limiter = Limiter(
    get_remote_address, app=app, default_limits=[], storage_uri="memory://"
)


@app.get("/")
def index() -> Any:
    """Serve the single static chat page (no framework, no build step)."""
    return send_from_directory(app.static_folder or "static", "index.html")


@app.get("/health")
def health() -> tuple:
    return jsonify({"ok": True}), 200


@app.post("/api/chat")
@limiter.limit("20 per minute; 200 per day")
def chat() -> tuple:
    body = request.get_json(silent=True) or {}
    message = body.get("message")
    if not message or not isinstance(message, str) or not message.strip():
        return jsonify({"error": "message is required"}), 400

    session_id = body.get("session_id") or str(uuid.uuid4())
    history = _history.setdefault(session_id, [])

    response = rag.answer(message, history=history)

    history.append({"role": "user", "content": message})
    history.append({"role": "assistant", "content": response})
    del history[:-_HISTORY_CAP]

    # Conversation logging: one JSONL line per exchange to stdout, captured by
    # Render's log dashboard (see ADR-0002) — no log file, no DB.
    print(
        json.dumps(
            {
                "session_id": session_id,
                "question": message,
                "answer": response,
                "ts": datetime.now(timezone.utc).isoformat(),
            }
        ),
        flush=True,
    )

    return jsonify({"response": response, "session_id": session_id}), 200
