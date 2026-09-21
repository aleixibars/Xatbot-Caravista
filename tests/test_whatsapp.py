"""Tests for the WhatsApp webhook — Graph API send and app.rag.answer mocked."""

import hashlib
import hmac
import json
import threading
import time

import pytest

import app.web as web
import app.whatsapp as whatsapp
from app import config


class _FakeResponse:
    status_code = 200
    text = "ok"


@pytest.fixture
def sent():
    return []


@pytest.fixture
def done():
    return threading.Event()


@pytest.fixture
def client(monkeypatch, sent, done):
    whatsapp._history.clear()
    whatsapp._seen_message_ids.clear()
    monkeypatch.setattr(config, "META_ACCESS_TOKEN", "test-access-token")
    monkeypatch.setattr(config, "META_PHONE_NUMBER_ID", "111222333")
    monkeypatch.setattr(config, "META_VERIFY_TOKEN", "verify-me")
    monkeypatch.setattr(config, "META_APP_SECRET", "app-secret")
    monkeypatch.setattr(config, "SKIP_SIGNATURE_VALIDATION", True)

    def fake_post(url, headers=None, json=None, timeout=None):
        sent.append({"url": url, "headers": headers, "json": json})
        done.set()
        return _FakeResponse()

    monkeypatch.setattr(whatsapp.httpx, "post", fake_post)
    monkeypatch.setattr(
        whatsapp.rag, "answer", lambda message, history=None: f"answer:{message}"
    )
    return web.app.test_client()


def _payload(body="hola", from_="34612345678"):
    """Realistic Meta Cloud API inbound-text webhook payload."""
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "WABA_ID",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "15550000000",
                                "phone_number_id": "111222333",
                            },
                            "contacts": [
                                {"profile": {"name": "Test"}, "wa_id": from_}
                            ],
                            "messages": [
                                {
                                    "from": from_,
                                    "id": f"wamid.{from_}.{body}",
                                    "timestamp": "1700000000",
                                    "type": "text",
                                    "text": {"body": body},
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }


def _status_payload():
    """Delivery-status update — has "statuses", no "messages"."""
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "WABA_ID",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "15550000000",
                                "phone_number_id": "111222333",
                            },
                            "statuses": [
                                {
                                    "id": "wamid.TEST",
                                    "status": "delivered",
                                    "timestamp": "1700000000",
                                    "recipient_id": "34612345678",
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }


def _post(test_client, body="hola", from_="34612345678", **kwargs):
    return test_client.post("/webhook", json=_payload(body, from_), **kwargs)


def test_webhook_acks_immediately_and_replies_in_background(client, sent, done):
    resp = _post(client)
    assert resp.status_code == 200
    assert resp.data == b""
    assert done.wait(timeout=2)
    assert sent == [
        {
            "url": "https://graph.facebook.com/v21.0/111222333/messages",
            "headers": {"Authorization": "Bearer test-access-token"},
            "json": {
                "messaging_product": "whatsapp",
                "to": "34612345678",
                "text": {"body": "answer:hola"},
            },
        }
    ]


def test_get_webhook_verification_returns_challenge(client):
    resp = client.get(
        "/webhook",
        query_string={
            "hub.mode": "subscribe",
            "hub.verify_token": "verify-me",
            "hub.challenge": "challenge-123",
        },
    )
    assert resp.status_code == 200
    assert resp.data == b"challenge-123"


def test_get_webhook_verification_wrong_token_403(client):
    resp = client.get(
        "/webhook",
        query_string={
            "hub.mode": "subscribe",
            "hub.verify_token": "wrong",
            "hub.challenge": "challenge-123",
        },
    )
    assert resp.status_code == 403


def test_webhook_status_update_acked_without_processing(client, sent):
    resp = client.post("/webhook", json=_status_payload())
    assert resp.status_code == 200
    assert sent == []


def test_webhook_batched_messages_all_answered(client, sent):
    # One payload can carry several queued messages (e.g. after a cold start).
    payload = _payload(body="una")
    payload["entry"][0]["changes"][0]["value"]["messages"].append(
        {
            "from": "34612345678",
            "id": "wamid.SECOND",
            "timestamp": "1700000001",
            "type": "text",
            "text": {"body": "dues"},
        }
    )
    resp = client.post("/webhook", json=payload)
    assert resp.status_code == 200
    deadline = time.monotonic() + 2
    while len(sent) < 2 and time.monotonic() < deadline:
        time.sleep(0.01)
    assert sorted(m["json"]["text"]["body"] for m in sent) == [
        "answer:dues",
        "answer:una",
    ]


def test_webhook_duplicate_message_id_ignored(client, sent, done):
    # Meta redelivers the same wamid when the ack arrives late (cold start) —
    # only the first delivery must be answered.
    _post(client)
    assert done.wait(timeout=2)
    done.clear()
    resp = _post(client)
    assert resp.status_code == 200
    assert not done.wait(timeout=0.3)
    assert len(sent) == 1


def test_webhook_missing_credentials_returns_error(client, monkeypatch):
    monkeypatch.setattr(config, "META_ACCESS_TOKEN", None)
    resp = _post(client)
    assert resp.status_code == 503
    assert "error" in resp.get_json()


def test_webhook_invalid_signature_403(client, monkeypatch, sent):
    monkeypatch.setattr(config, "SKIP_SIGNATURE_VALIDATION", False)
    resp = client.post(
        "/webhook",
        data=json.dumps(_payload()),
        content_type="application/json",
        headers={"X-Hub-Signature-256": "sha256=bogus"},
    )
    assert resp.status_code == 403
    assert sent == []


def test_webhook_valid_signature_accepted(client, monkeypatch, done):
    # Signature is HMAC-SHA256 over the raw request bytes with META_APP_SECRET.
    monkeypatch.setattr(config, "SKIP_SIGNATURE_VALIDATION", False)
    raw = json.dumps(_payload()).encode()
    signature = (
        "sha256=" + hmac.new(b"app-secret", raw, hashlib.sha256).hexdigest()
    )
    resp = client.post(
        "/webhook",
        data=raw,
        content_type="application/json",
        headers={"X-Hub-Signature-256": signature},
    )
    assert resp.status_code == 200
    assert done.wait(timeout=2)


def test_webhook_non_text_message_gets_friendly_reply(client, monkeypatch, sent, done):
    calls: list = []
    monkeypatch.setattr(
        whatsapp.rag,
        "answer",
        lambda message, history=None: calls.append(message) or "answer",
    )
    payload = _payload()
    message = payload["entry"][0]["changes"][0]["value"]["messages"][0]
    message["type"] = "audio"
    del message["text"]
    message["audio"] = {"id": "media-id"}
    resp = client.post("/webhook", json=payload)
    assert resp.status_code == 200
    assert done.wait(timeout=2)
    assert calls == []
    assert sent[0]["json"]["text"]["body"] == (
        "De moment només puc llegir missatges de text 🙂"
    )


def test_webhook_empty_body_ignored(client, sent):
    resp = _post(client, body="   ")
    assert resp.status_code == 200
    assert sent == []


def test_webhook_keeps_history_per_phone(client, sent, done):
    captured: list = []

    def fake_answer(message, history=None):
        captured.append(list(history or []))
        return f"answer:{message}"

    whatsapp.rag.answer = fake_answer  # already monkeypatched attr; safe to swap
    _post(client, body="primera")
    assert done.wait(timeout=2)
    done.clear()
    _post(client, body="segona")
    assert done.wait(timeout=2)

    assert captured[0] == []
    assert captured[1] == [
        {"role": "user", "content": "primera"},
        {"role": "assistant", "content": "answer:primera"},
    ]


def test_webhook_truncates_reply_at_sentence_boundary(client, monkeypatch, sent, done):
    long_reply = "Frase curta. " * 400  # ~5200 chars, over the 4096 limit
    monkeypatch.setattr(
        whatsapp.rag, "answer", lambda message, history=None: long_reply
    )
    _post(client)
    assert done.wait(timeout=2)
    body = sent[0]["json"]["text"]["body"]
    assert len(body) <= 4096
    assert body.endswith("Frase curta.")


def test_webhook_truncation_preserves_disclaimer(client, monkeypatch, sent, done):
    from app import rag

    long_reply = "Frase curta. " * 400 + rag.DISCLAIMER
    monkeypatch.setattr(
        whatsapp.rag, "answer", lambda message, history=None: long_reply
    )
    _post(client)
    assert done.wait(timeout=2)
    body = sent[0]["json"]["text"]["body"]
    assert len(body) <= 4096
    assert body.endswith(rag.DISCLAIMER)
    assert "Frase curta." in body


def test_webhook_converts_markdown_bold_to_whatsapp_bold(client, monkeypatch, sent, done):
    # Issue #49: WhatsApp bold is *single asterisks* — Markdown **bold** shows
    # as literal asterisks in the chat.
    monkeypatch.setattr(
        whatsapp.rag,
        "answer",
        lambda message, history=None: "Truquem al **973 000 000** o per **WhatsApp**.",
    )
    _post(client)
    assert done.wait(timeout=2)
    assert sent[0]["json"]["text"]["body"] == (
        "Truquem al *973 000 000* o per *WhatsApp*."
    )


def test_webhook_truncation_drops_dangling_bold_marker(client, monkeypatch, sent, done):
    # Issue #49: if truncation cuts mid-bold-span, the lone trailing "**" must
    # not survive as a dangling asterisk that breaks the message's rendering.
    long_reply = "x" * 4094 + "**" + "negreta que el tall deixa fora"
    monkeypatch.setattr(
        whatsapp.rag, "answer", lambda message, history=None: long_reply
    )
    _post(client)
    assert done.wait(timeout=2)
    body = sent[0]["json"]["text"]["body"]
    assert len(body) <= 4096
    assert "*" not in body


def test_to_whatsapp_markdown_drops_mid_text_dangling_marker():
    # Issue #49: _truncate cuts at a sentence boundary, so a cut inside a bold
    # span usually leaves the unpaired "**" mid-text (closer fell after the
    # boundary), not at the very end — it must not survive as literal
    # asterisks.
    assert (
        whatsapp._to_whatsapp_markdown("Atenció: **el límit és 85.000 €.")
        == "Atenció: el límit és 85.000 €."
    )


def test_to_whatsapp_markdown_balanced_spans_with_dangling_opener():
    # Balanced spans before the cut must still convert; only the unpaired
    # opener is dropped.
    assert (
        whatsapp._to_whatsapp_markdown("El **mínim** és X. Vegeu **la taula 3.")
        == "El *mínim* és X. Vegeu la taula 3."
    )


def test_webhook_reply_keeps_newlines(client, monkeypatch, sent, done):
    # Cloud API text sends are plain body — formatting must survive.
    monkeypatch.setattr(
        whatsapp.rag, "answer", lambda message, history=None: "Línia u.\nLínia dos."
    )
    _post(client)
    assert done.wait(timeout=2)
    assert sent[0]["json"]["text"]["body"] == "Línia u.\nLínia dos."


def test_webhook_rag_error_sends_catalan_fallback(client, monkeypatch, sent, done):
    def boom(message, history=None):
        raise RuntimeError("rag exploded")

    monkeypatch.setattr(whatsapp.rag, "answer", boom)
    _post(client)
    assert done.wait(timeout=2)
    assert sent[0]["json"]["text"]["body"] == (
        "Ho sento, hi ha hagut un problema. Torna-ho a provar en un moment."
    )


def test_webhook_send_error_logs_status_and_body(client, monkeypatch, done, capsys):
    class _ErrorResponse:
        status_code = 401
        text = '{"error": {"message": "Invalid OAuth access token"}}'

    def fake_post(url, headers=None, json=None, timeout=None):
        done.set()
        return _ErrorResponse()

    monkeypatch.setattr(whatsapp.httpx, "post", fake_post)
    _post(client)
    assert done.wait(timeout=2)
    out = capsys.readouterr().out
    assert "send_error" in out
    assert "401" in out
    assert "Invalid OAuth access token" in out


def test_webhook_logs_mask_phone_number(client, sent, done, capsys):
    _post(client)
    assert done.wait(timeout=2)
    out = capsys.readouterr().out
    assert "34612345678" not in out
    assert "612345" not in out


def test_webhook_logs_question_and_answer(client, sent, done, capsys):
    # ADR-0002: each exchange (question + answer) logged as JSONL to stdout.
    _post(client, body="quins horaris teniu?")
    assert done.wait(timeout=2)
    out = capsys.readouterr().out
    assert "quins horaris teniu?" in out
    assert "answer:quins horaris teniu?" in out
