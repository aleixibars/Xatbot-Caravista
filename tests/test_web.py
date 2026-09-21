"""Tests for Flask routes — app.rag.answer mocked, no real LLM/Qdrant."""

import json

import pytest

import app.web as web


@pytest.fixture
def client(monkeypatch):
    web._history.clear()
    monkeypatch.setattr(web.rag, "answer", lambda message, history=None: f"answer:{message}")
    # Disable the rate limiter here: it shares one in-memory per-IP bucket across
    # all requests in the process, so accumulating test calls would eventually 429.
    monkeypatch.setattr(web.limiter, "enabled", False)
    return web.app.test_client()


def test_index_serves_html(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.content_type
    assert b"chat-form" in resp.data
    assert b"/static/app.js" in resp.data
    # The page is a WhatsApp-shaped conversation with Caravista, so the
    # contact name and the composer must both be in the served HTML.
    assert b"Caravista" in resp.data
    assert b'id="messages"' in resp.data
    assert b'class="composer"' in resp.data


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.get_json() == {"ok": True}


def test_chat_empty_message_400(client):
    resp = client.post("/api/chat", json={"message": "   "})
    assert resp.status_code == 400


def test_chat_missing_message_400(client):
    resp = client.post("/api/chat", json={})
    assert resp.status_code == 400


def test_chat_generates_session_id(client):
    resp = client.post("/api/chat", json={"message": "hola"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["response"] == "answer:hola"
    assert data["session_id"]


def test_chat_history_caps_at_20(client):
    session_id = "fixed-session"
    for i in range(15):
        resp = client.post("/api/chat", json={"message": f"m{i}", "session_id": session_id})
        assert resp.status_code == 200
    # 15 exchanges = 30 messages, capped to the last 20.
    assert len(web._history[session_id]) == 20


def test_chat_logs_exchange_as_jsonl(client, capsys):
    resp = client.post("/api/chat", json={"message": "hola", "session_id": "s1"})
    assert resp.status_code == 200
    lines = [ln for ln in capsys.readouterr().out.splitlines() if ln.strip()]
    entry = json.loads(lines[-1])
    assert entry["session_id"] == "s1"
    assert entry["question"] == "hola"
    assert entry["answer"] == "answer:hola"
    assert entry["ts"]


def test_chat_rate_limited_after_20_per_minute(monkeypatch):
    # Exercise the real limiter (the `client` fixture disables it). One in-memory
    # per-IP bucket; the test client's IP is constant, so 20 pass then 429.
    web._history.clear()
    monkeypatch.setattr(web.rag, "answer", lambda message, history=None: f"answer:{message}")
    web.limiter.reset()
    test_client = web.app.test_client()
    codes = [
        test_client.post("/api/chat", json={"message": "hola"}).status_code
        for _ in range(21)
    ]
    assert codes[:20] == [200] * 20
    assert codes[20] == 429
    web.limiter.reset()
