"""WhatsApp channel via Meta's Cloud API (issue #47, replaces the Twilio PoC).

Thin webhook layer over the existing RAG pipeline: validates Meta's
``X-Hub-Signature-256``, acks immediately, and answers in a background thread
(gunicorn runs threaded sync workers, so a daemon ``threading.Thread`` is the
"don't block Meta" mechanism here — no async framework involved). Outbound
sends go through the Graph API with ``httpx``.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import threading
import time
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any

import httpx
from flask import Blueprint, jsonify, request

from app import config, rag

whatsapp_bp = Blueprint("whatsapp", __name__)

# Per-phone-number history, in-process only — same pattern and cap as
# app/web.py's per-session `_history` (see ADR-0002).
_history: dict[str, list[dict]] = {}
_HISTORY_CAP: int = 20

# The Cloud API rejects text bodies longer than this.
_WHATSAPP_CHAR_LIMIT: int = 4096

# Recently seen message ids (wamid) — Meta redelivers a webhook when the 200
# arrives late (e.g. a Render cold start, see README_WHATSAPP.md), and each
# duplicate would trigger a paid RAG call plus a duplicate reply. In-process
# only, same trade-off as `_history`.
_seen_message_ids: OrderedDict[str, None] = OrderedDict()
_SEEN_CAP: int = 256

_GRAPH_URL: str = "https://graph.facebook.com/v21.0"

_FALLBACK_MESSAGE: str = (
    "Ho sento, hi ha hagut un problema. Torna-ho a provar en un moment."
)

_UNSUPPORTED_TYPE_MESSAGE: str = "De moment només puc llegir missatges de text 🙂"


def _mask_phone(phone: str) -> str:
    """Mask a `34612345678` sender: keep country code (first two digits) and
    last three, never log the full number."""
    prefix, _, number = phone.rpartition(":")
    digits = number.lstrip("+")
    if len(digits) <= 5:
        masked = "*" * len(digits)
    else:
        masked = digits[:2] + "*" * (len(digits) - 5) + digits[-3:]
    return f"{prefix}:+{masked}" if prefix else f"+{masked}"


def _truncate(text: str) -> str:
    """Cap at the Cloud API's text limit, cutting the answer body at the last
    complete sentence boundary rather than mid-word. The disclaimer suffix,
    when present (advice-adjacent answers, issue #49), is preserved through
    truncation."""
    if len(text) <= _WHATSAPP_CHAR_LIMIT:
        return text
    suffix = rag.DISCLAIMER if text.endswith(rag.DISCLAIMER) else ""
    clipped = text[: _WHATSAPP_CHAR_LIMIT - len(suffix)]
    boundary = max(clipped.rfind(end) for end in (".", "!", "?", "\n"))
    body = clipped[: boundary + 1].rstrip() if boundary > 0 else clipped
    return body + suffix


def _to_whatsapp_markdown(text: str) -> str:
    """Convert Markdown bold to WhatsApp's syntax: ``**text**`` → ``*text*``
    (issue #49). WhatsApp renders double asterisks as literal characters.

    Applied after :func:`_truncate` (so truncation counts real characters); an
    unpaired ``**`` left by a truncation that cut mid-bold-span — trailing, or
    mid-text when the cut landed at a sentence boundary inside the span — is
    dropped so no dangling asterisks break the rest of the rendering."""
    if text.count("**") % 2 == 1:
        head, _, tail = text.rpartition("**")
        text = (head + tail).rstrip()
    return re.sub(r"\*\*(.+?)\*\*", r"*\1*", text)


def _log(event: str, phone: str, **fields: Any) -> None:
    print(
        json.dumps(
            {
                "channel": "whatsapp",
                "event": event,
                "from": _mask_phone(phone),
                "ts": datetime.now(timezone.utc).isoformat(),
                **fields,
            }
        ),
        flush=True,
    )


def _send(to: str, text: str) -> bool:
    """Send a text message via the Graph API. Returns False (after logging
    Meta's status and response body — its errors are descriptive) on any
    non-200 response."""
    response = httpx.post(
        f"{_GRAPH_URL}/{config.META_PHONE_NUMBER_ID}/messages",
        headers={"Authorization": f"Bearer {config.META_ACCESS_TOKEN}"},
        json={"messaging_product": "whatsapp", "to": to, "text": {"body": text}},
        timeout=30,
    )
    if response.status_code != 200:
        _log("send_error", to, status=response.status_code, response=response.text)
        return False
    return True


def _answer_and_reply(body: str, sender: str) -> None:
    """Background worker: RAG answer + Graph API send. Never raises — Meta has
    already been acked, so errors turn into a friendly fallback message."""
    started = time.monotonic()
    try:
        history = _history.setdefault(sender, [])
        reply = _truncate(rag.answer(body, history=history))
        history.append({"role": "user", "content": body})
        history.append({"role": "assistant", "content": reply})
        del history[:-_HISTORY_CAP]
    except Exception as exc:  # noqa: BLE001 — last-resort guard, see docstring
        _log("rag_error", sender, error=repr(exc))
        reply = _FALLBACK_MESSAGE
    rag_seconds = round(time.monotonic() - started, 2)
    # WhatsApp-channel formatting only — history above keeps the RAG's
    # standard Markdown (the shared format across channels, issue #49).
    reply = _to_whatsapp_markdown(reply)
    # question/answer on the exchange log line per ADR-0002 (conversation
    # logging to stdout JSONL, same as app/web.py's /api/chat line).
    try:
        if _send(sender, reply):
            _log(
                "outbound",
                sender,
                rag_seconds=rag_seconds,
                question=body,
                answer=reply,
            )
    except Exception as exc:  # noqa: BLE001
        _log(
            "send_error",
            sender,
            error=repr(exc),
            rag_seconds=rag_seconds,
            question=body,
            answer=reply,
        )


def _reply_unsupported(sender: str) -> None:
    try:
        _send(sender, _UNSUPPORTED_TYPE_MESSAGE)
    except Exception as exc:  # noqa: BLE001 — background thread, never raises
        _log("send_error", sender, error=repr(exc))


def _valid_signature(raw_body: bytes) -> bool:
    """Meta signs the raw request bytes: ``X-Hub-Signature-256`` is
    ``"sha256=" + HMAC-SHA256(raw_body, META_APP_SECRET)``."""
    if not config.META_APP_SECRET:
        return False
    expected = "sha256=" + hmac.new(
        config.META_APP_SECRET.encode(), raw_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(
        expected, request.headers.get("X-Hub-Signature-256", "")
    )


@whatsapp_bp.get("/webhook")
def verify() -> tuple:
    """Meta's webhook verification handshake: echo `hub.challenge` as plain
    text when the verify token matches."""
    if (
        request.args.get("hub.mode") == "subscribe"
        and config.META_VERIFY_TOKEN
        and request.args.get("hub.verify_token") == config.META_VERIFY_TOKEN
    ):
        return request.args.get("hub.challenge", ""), 200
    return jsonify({"error": "webhook verification failed"}), 403


@whatsapp_bp.post("/webhook")
def webhook() -> tuple:
    if not config.META_ACCESS_TOKEN or not config.META_PHONE_NUMBER_ID:
        return (
            jsonify(
                {
                    "error": "WhatsApp is not configured "
                    "(set META_ACCESS_TOKEN and META_PHONE_NUMBER_ID)"
                }
            ),
            503,
        )

    # Raw bytes must be captured before Flask parses the JSON — the signature
    # is computed over them.
    raw_body = request.get_data()
    if not config.SKIP_SIGNATURE_VALIDATION and not _valid_signature(raw_body):
        return jsonify({"error": "invalid signature"}), 403

    data = request.get_json(silent=True) or {}
    # Meta batches: one payload can carry several entries/changes/messages
    # (e.g. everything queued while the service was cold). Handle each one;
    # a change without "messages" is a delivery-status update (`statuses`:
    # sent/delivered/read) — nothing to answer.
    try:
        for entry in data.get("entry") or []:
            for change in entry.get("changes") or []:
                for message in (change.get("value") or {}).get("messages") or []:
                    _handle_message(message)
    except (AttributeError, TypeError):
        # Malformed payload shape — still ack, Meta retries otherwise.
        pass

    # Meta just needs a fast 200 ack; the reply goes out via the Graph API.
    return "", 200


def _handle_message(message: dict) -> None:
    sender = str(message.get("from", ""))
    if not sender:
        return

    message_id = message.get("id")
    if message_id:
        if message_id in _seen_message_ids:
            # Don't log the wamid itself — it base64-encodes the phone number.
            _log("duplicate", sender)
            return
        _seen_message_ids[message_id] = None
        while len(_seen_message_ids) > _SEEN_CAP:
            _seen_message_ids.popitem(last=False)

    if message.get("type") != "text":
        _log("unsupported_type", sender, type=message.get("type"))
        threading.Thread(
            target=_reply_unsupported, args=(sender,), daemon=True
        ).start()
        return

    body = message.get("text", {}).get("body", "").strip()
    if not body:
        return

    _log("inbound", sender)
    threading.Thread(
        target=_answer_and_reply, args=(body, sender), daemon=True
    ).start()
