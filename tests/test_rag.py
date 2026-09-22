"""Unit tests for app.rag — all external clients mocked, no network."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import app.rag as rag


def _point(score, text="frag text", source="src.pdf"):
    return SimpleNamespace(score=score, payload={"text": text, "source": source})


def test_search_filters_by_min_score(monkeypatch):
    monkeypatch.setattr(rag, "_ensure_collection", lambda: None)
    monkeypatch.setattr(rag, "embed", lambda text: [0.0] * 1536)

    qdrant = MagicMock()
    qdrant.query_points.return_value = SimpleNamespace(
        points=[
            _point(0.9, text="keep me"),
            _point(rag.SEARCH_MIN_SCORE - 0.01, text="drop me"),
            _point(rag.SEARCH_MIN_SCORE, text="keep edge"),
        ]
    )
    monkeypatch.setattr(rag, "_qdrant_client", lambda: qdrant)

    fragments = rag.search("una pregunta")

    assert [f["text"] for f in fragments] == ["keep me", "keep edge"]
    assert fragments[0] == {"text": "keep me", "source": "src.pdf"}


def test_search_retrieval_knobs_widened_for_issue_32(monkeypatch):
    # Issue #32: two live misses were caused by relevant fragments either not
    # making the candidate list or being dropped by a too-strict score floor.
    monkeypatch.setattr(rag, "_ensure_collection", lambda: None)
    monkeypatch.setattr(rag, "embed", lambda text: [0.0] * 1536)

    qdrant = MagicMock()
    qdrant.query_points.return_value = SimpleNamespace(points=[])
    monkeypatch.setattr(rag, "_qdrant_client", lambda: qdrant)

    rag.search("una pregunta")

    assert qdrant.query_points.call_args.kwargs["limit"] == 10
    assert rag.SEARCH_MIN_SCORE == 0.25


def test_answer_normal_path_appends_disclaimer(monkeypatch):
    monkeypatch.setattr(rag, "search", lambda q, *a, **k: [{"text": "el context", "source": "s"}])

    chat_client = MagicMock()
    chat_client.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="La resposta."))]
    )
    monkeypatch.setattr(rag, "_deepseek_client", lambda: chat_client)

    result = rag.answer("Quant és l'IVA?")

    assert result.startswith("La resposta.")
    assert result.endswith(rag.DISCLAIMER)
    # Chat model was actually consulted on the normal path.
    assert chat_client.chat.completions.create.called


def test_answer_system_prompt_positions_bot_as_caravista_assistant(monkeypatch):
    monkeypatch.setattr(rag, "route", lambda q: "rag")
    monkeypatch.setattr(rag, "search", lambda q, *a, **k: [{"text": "el context", "source": "s"}])

    chat_client = MagicMock()
    chat_client.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="La resposta."))]
    )
    monkeypatch.setattr(rag, "_deepseek_client", lambda: chat_client)

    result = rag.answer("Quins serveis oferiu?")

    system = chat_client.chat.completions.create.call_args.kwargs["messages"][0]["content"]
    # The bot is Caravista's own assistant for questions about the company and
    # its services, not a generic subject-matter expert.
    assert "Caravista" in system
    assert "serveis" in system
    # The grounding instructions (ADR-0002) must not regress: answer only from
    # CONTEXT, and never invent facts.
    assert "CONTEXT" in system
    assert "No inventis" in system
    # And every answer still carries the fixed disclaimer.
    assert result.endswith(rag.DISCLAIMER)


def test_answer_no_fragments_skips_chat_model(monkeypatch):
    monkeypatch.setattr(rag, "route", lambda q: "rag")
    monkeypatch.setattr(rag, "search", lambda q, *a, **k: [])
    chat_client = MagicMock()
    monkeypatch.setattr(rag, "_deepseek_client", lambda: chat_client)

    result = rag.answer("Pregunta desconeguda")

    assert result == rag.NO_CONTEXT_MESSAGE + rag.DISCLAIMER
    assert result.endswith(rag.DISCLAIMER)
    chat_client.chat.completions.create.assert_not_called()


def _chat_response(content):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )


def test_system_prompt_forbids_model_written_disclaimer():
    # Issue #49: the app appends the official DISCLAIMER in code, so the model
    # writing its own closing caveat produced a double disclaimer live. The
    # prompt must forbid it explicitly (the live prompt-following itself is not
    # unit-testable — this pins the instruction, not the behaviour).
    assert "descàrrec" in rag.SYSTEM_PROMPT
    assert "ja afegeix" in rag.SYSTEM_PROMPT


def _label_setup(monkeypatch, label):
    """Mock route + the SQL/vector sources so any label yields context."""
    monkeypatch.setattr(rag, "route", lambda q: label)
    monkeypatch.setattr(
        rag.db, "get_company_info", lambda keys=None, **k: [{"key": "k", "value": "v"}]
    )
    monkeypatch.setattr(
        rag.db,
        "search_team",
        lambda text, **k: [{"name": "N", "role": "R", "department": "D"}],
    )
    monkeypatch.setattr(
        rag.db,
        "list_services",
        lambda **k: [{"name": "S", "one_liner": "O", "url": "/s"}],
    )
    monkeypatch.setattr(
        rag.db, "match_routing_rule", lambda text, **k: [{"area": "A", "bot_action": "B"}]
    )
    monkeypatch.setattr(
        rag.db, "search_faq", lambda text, **k: [{"question": "Q", "answer": "A"}]
    )
    monkeypatch.setattr(rag, "search", lambda q, *a, **k: [{"text": "frag", "source": "s"}])

    chat_client = MagicMock()
    chat_client.chat.completions.create.return_value = _chat_response("Resposta.")
    monkeypatch.setattr(rag, "_deepseek_client", lambda: chat_client)


@pytest.mark.parametrize("label", ["company_info", "team_members", "services"])
def test_answer_factual_labels_skip_disclaimer(monkeypatch, label):
    # Issue #49: pure-fact labels (opening hours, who works here, service list)
    # carry no advice risk — the disclaimer is noise there.
    _label_setup(monkeypatch, label)

    result = rag.answer("Pregunta factual")

    assert result == "Resposta."
    assert not result.endswith(rag.DISCLAIMER)


@pytest.mark.parametrize("label", ["routing_rules", "faq", "rag"])
def test_answer_advice_adjacent_labels_keep_disclaimer(monkeypatch, label):
    # Issue #49: routing guidance, FAQ content (audit thresholds, escalation)
    # and narrative RAG answers can resemble advice — keep the disclaimer.
    _label_setup(monkeypatch, label)

    result = rag.answer("Pregunta amb possible consell")

    assert result == "Resposta." + rag.DISCLAIMER


def test_answer_fact_label_vector_fallback_keeps_disclaimer(monkeypatch):
    # Issue #49: a pure-fact label whose table matches nothing falls through
    # to the vector search — the answer is then the same narrative KB content
    # as "rag", so the disclaimer must follow the content, not the label.
    _label_setup(monkeypatch, "team_members")
    monkeypatch.setattr(rag.db, "search_team", lambda text, **k: [])

    result = rag.answer("Pregunta sense fila a la taula")

    assert result == "Resposta." + rag.DISCLAIMER


def test_route_returns_valid_label(monkeypatch):
    chat_client = MagicMock()
    chat_client.chat.completions.create.return_value = _chat_response("  FAQ \n")
    monkeypatch.setattr(rag, "_deepseek_client", lambda: chat_client)

    assert rag.route("Quins horaris teniu?") == "faq"


def test_route_label_with_preamble_still_matches(monkeypatch):
    chat_client = MagicMock()
    chat_client.chat.completions.create.return_value = _chat_response(
        "La resposta és: company_info"
    )
    monkeypatch.setattr(rag, "_deepseek_client", lambda: chat_client)

    assert rag.route("On és l'oficina?") == "company_info"


def test_route_label_with_trailing_punctuation_still_matches(monkeypatch):
    chat_client = MagicMock()
    chat_client.chat.completions.create.return_value = _chat_response("faq.")
    monkeypatch.setattr(rag, "_deepseek_client", lambda: chat_client)

    assert rag.route("On sou i quin horari feu?") == "faq"


def test_route_clean_classification_logs_nothing(monkeypatch, capsys):
    # Issue #19: only *fallback* paths log — a clean label (including a clean
    # "rag") must stay silent so production logs only show anomalies.
    chat_client = MagicMock()
    monkeypatch.setattr(rag, "_deepseek_client", lambda: chat_client)

    for content, expected in [("faq", "faq"), ("rag", "rag")]:
        chat_client.chat.completions.create.return_value = _chat_response(content)
        assert rag.route("qualsevol cosa") == expected

    assert capsys.readouterr().out == ""


def test_route_garbage_response_defaults_to_rag(monkeypatch):
    chat_client = MagicMock()
    chat_client.chat.completions.create.return_value = _chat_response("banana split")
    monkeypatch.setattr(rag, "_deepseek_client", lambda: chat_client)

    assert rag.route("qualsevol cosa") == "rag"


def test_route_garbage_response_logs_fallback(monkeypatch, capsys):
    chat_client = MagicMock()
    chat_client.chat.completions.create.return_value = _chat_response("banana split")
    monkeypatch.setattr(rag, "_deepseek_client", lambda: chat_client)

    rag.route("qualsevol cosa")

    assert capsys.readouterr().out.strip() != ""


def test_route_api_error_defaults_to_rag(monkeypatch):
    chat_client = MagicMock()
    chat_client.chat.completions.create.side_effect = RuntimeError("router down")
    monkeypatch.setattr(rag, "_deepseek_client", lambda: chat_client)

    assert rag.route("qualsevol cosa") == "rag"


def test_route_api_error_logs_fallback(monkeypatch, capsys):
    chat_client = MagicMock()
    chat_client.chat.completions.create.side_effect = RuntimeError("router down")
    monkeypatch.setattr(rag, "_deepseek_client", lambda: chat_client)

    rag.route("qualsevol cosa")

    assert capsys.readouterr().out.strip() != ""


def test_answer_company_info_from_db_skips_search(monkeypatch):
    monkeypatch.setattr(rag, "route", lambda q: "company_info")
    monkeypatch.setattr(
        rag.db,
        "get_company_info",
        lambda keys=None, **k: [{"key": "phone", "value": "973 000 000"}],
    )
    search = MagicMock()
    monkeypatch.setattr(rag, "search", search)

    chat_client = MagicMock()
    chat_client.chat.completions.create.return_value = _chat_response("El telèfon.")
    monkeypatch.setattr(rag, "_deepseek_client", lambda: chat_client)

    result = rag.answer("Quin és el vostre telèfon?")

    # Pure-fact label — no disclaimer since issue #49.
    assert result == "El telèfon."
    search.assert_not_called()
    prompt = chat_client.chat.completions.create.call_args.kwargs["messages"][-1]["content"]
    assert "phone: 973 000 000" in prompt


def test_answer_routing_rules_context_carries_real_phone(monkeypatch):
    # Issue #41: a routing_rules row has no contact data, so the model invented
    # a plausible-looking phone number. The real contact facts must always be
    # appended to the CONTEXT so there is nothing left to fabricate.
    # A fixture stand-in for the client's company_info rows: the real seed
    # (app/db_seed.py) is client data and may be empty, and what is under test
    # here is that whatever contact facts exist reach the CONTEXT.
    contact = {key: f"valor-{key}" for key in rag._CONTACT_KEYS}

    monkeypatch.setattr(rag, "route", lambda q: "routing_rules")
    monkeypatch.setattr(
        rag.db,
        "match_routing_rule",
        lambda text, **k: [{"area": "Herències", "bot_action": "Parlar amb l'àrea jurídica."}],
    )
    monkeypatch.setattr(
        rag.db,
        "get_company_info",
        lambda keys=None, **k: [
            {"key": key, "value": contact[key]}
            for key in (keys if keys is not None else contact)
        ],
    )
    search = MagicMock()
    monkeypatch.setattr(rag, "search", search)

    chat_client = MagicMock()
    chat_client.chat.completions.create.return_value = _chat_response("Resposta.")
    monkeypatch.setattr(rag, "_deepseek_client", lambda: chat_client)

    result = rag.answer("Com repartim l'herència de l'empresa familiar?")

    assert result == "Resposta." + rag.DISCLAIMER
    search.assert_not_called()
    prompt = chat_client.chat.completions.create.call_args.kwargs["messages"][-1]["content"]
    assert "Àrea Herències: Parlar amb l'àrea jurídica." in prompt
    # The real values are present in the CONTEXT — not merely "no wrong number".
    for key in rag._CONTACT_KEYS:
        assert contact[key] in prompt, key


def test_answer_survives_contact_lookup_failure(monkeypatch, capsys):
    # The contact block (issue #41) is an enhancement: if the SQLite lookup
    # fails, the answer must still go out (the "rag" route never needed the DB
    # before) and the fallback must be logged, mirroring route() (issue #19).
    monkeypatch.setattr(rag, "route", lambda q: "rag")
    monkeypatch.setattr(rag, "search", lambda q, *a, **k: [{"text": "fragment", "source": "s"}])
    monkeypatch.setattr(
        rag.db,
        "get_company_info",
        MagicMock(side_effect=RuntimeError("db unavailable")),
    )

    chat_client = MagicMock()
    chat_client.chat.completions.create.return_value = _chat_response("Resposta.")
    monkeypatch.setattr(rag, "_deepseek_client", lambda: chat_client)

    result = rag.answer("Pregunta general d'IVA")

    assert result == "Resposta." + rag.DISCLAIMER
    prompt = chat_client.chat.completions.create.call_args.kwargs["messages"][-1]["content"]
    assert "Contacte:" not in prompt
    assert "contact_context_fallback" in capsys.readouterr().out


def test_answer_faq_no_rows_falls_through_to_search(monkeypatch):
    monkeypatch.setattr(rag, "route", lambda q: "faq")
    monkeypatch.setattr(rag.db, "search_faq", lambda text, **k: [])
    search = MagicMock(return_value=[{"text": "fragment", "source": "s"}])
    monkeypatch.setattr(rag, "search", search)

    chat_client = MagicMock()
    chat_client.chat.completions.create.return_value = _chat_response("Resposta.")
    monkeypatch.setattr(rag, "_deepseek_client", lambda: chat_client)

    result = rag.answer("Pregunta sense FAQ")

    assert result == "Resposta." + rag.DISCLAIMER
    search.assert_called_once()


def test_answer_services_combines_sql_rows_and_fragments(monkeypatch):
    monkeypatch.setattr(rag, "route", lambda q: "services")
    monkeypatch.setattr(
        rag.db,
        "list_services",
        lambda **k: [
            {"name": "Auditoria", "one_liner": "Comptes anuals", "url": "/auditoria"}
        ],
    )
    search = MagicMock(return_value=[{"text": "Llindar auditoria: 2.850.000 €", "source": "s"}])
    monkeypatch.setattr(rag, "search", search)

    chat_client = MagicMock()
    chat_client.chat.completions.create.return_value = _chat_response("Resposta.")
    monkeypatch.setattr(rag, "_deepseek_client", lambda: chat_client)

    result = rag.answer("A partir de quina facturació cal auditoria?")

    # Pure-fact label — no disclaimer since issue #49.
    assert result == "Resposta."
    search.assert_called_once()
    prompt = chat_client.chat.completions.create.call_args.kwargs["messages"][-1]["content"]
    assert "Auditoria: Comptes anuals (/auditoria)" in prompt
    assert "Llindar auditoria: 2.850.000 €" in prompt


def test_answer_services_no_fragments_uses_sql_rows_alone(monkeypatch):
    monkeypatch.setattr(rag, "route", lambda q: "services")
    monkeypatch.setattr(
        rag.db,
        "list_services",
        lambda **k: [
            {"name": "Fiscal", "one_liner": "Impostos", "url": "/fiscal"}
        ],
    )
    search = MagicMock(return_value=[])
    monkeypatch.setattr(rag, "search", search)

    chat_client = MagicMock()
    chat_client.chat.completions.create.return_value = _chat_response("Resposta.")
    monkeypatch.setattr(rag, "_deepseek_client", lambda: chat_client)

    result = rag.answer("Quins serveis oferiu?")

    # Empty search must not become a NO_CONTEXT failure — SQL rows suffice.
    # Pure-fact label — no disclaimer since issue #49.
    assert result == "Resposta."
    prompt = chat_client.chat.completions.create.call_args.kwargs["messages"][-1]["content"]
    assert "Fiscal: Impostos (/fiscal)" in prompt


def test_answer_rag_label_goes_straight_to_search(monkeypatch):
    monkeypatch.setattr(rag, "route", lambda q: "rag")
    search = MagicMock(return_value=[{"text": "fragment", "source": "s"}])
    monkeypatch.setattr(rag, "search", search)
    db_mock = MagicMock()
    monkeypatch.setattr(rag, "db", db_mock)

    chat_client = MagicMock()
    chat_client.chat.completions.create.return_value = _chat_response("Resposta.")
    monkeypatch.setattr(rag, "_deepseek_client", lambda: chat_client)

    result = rag.answer("Pregunta general d'IVA")

    assert result == "Resposta." + rag.DISCLAIMER
    search.assert_called_once()
    # A "rag" label must not touch the SQL tables for context — the only
    # allowed lookup is the always-appended contact block (issue #41).
    assert {c[0] for c in db_mock.mock_calls} <= {"get_company_info", "get_company_info().__iter__"}
