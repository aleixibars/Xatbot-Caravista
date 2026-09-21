"""Tests for app/db.py — always against a temp DB file, never data/caravista.db.

The seed constants in ``app/db_seed.py`` are the client's real facts (and are
empty placeholders until Caravista's are filled in), so every test here swaps
them for the small fixture dataset below. That keeps the assertions about
``app/db.py``'s matching behaviour — the thing under test — rather than about
whichever client the repo is currently serving.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app import db, db_seed

TABLES = ["company_info", "team_members", "services", "routing_rules", "faq", "links"]

FIXTURE_COMPANY_INFO: dict[str, str] = {
    "brand_name": "Caravista (fixture)",
    "phone_main": "900 000 000",
    "location": "Vilafixture",
    "hours_mon_thu": "9:00-18:00",
}

FIXTURE_TEAM_MEMBERS: list[tuple[str, str, str]] = [
    ("Núria Exemple", "Tècnica · Administradora de finques", "Jurídic"),
    ("Mar Corella", "Gestió laboral", "Laboral"),
    ("Pau Corella", "Direcció", "Laboral"),
    ("Ona Vidal", "Comptable", "Fiscal"),
]

FIXTURE_SERVICES: list[tuple[str, str, str, str]] = [
    ("alfa", "Servei Alfa", "Primer servei de prova.", "https://example.test/alfa"),
    ("beta", "Servei Beta", "Segon servei de prova.", "https://example.test/beta"),
]

FIXTURE_ROUTING_RULES: list[tuple[str, str, str]] = [
    ("vull contractar personal, una nòmina", "Laboral", "Explica el servei i ofereix cita"),
    ("vull constituir societat, crear una empresa", "Jurídic", "Explica i ofereix cita"),
    ("renda / irpf", "Fiscal", "Explica el servei"),
]

FIXTURE_FAQ: list[tuple[str, str]] = [
    ("Quin horari feu?", "De dilluns a divendres."),
    ("Com puc deixar/veure ressenyes?", "A la nostra fitxa de Google."),
]

FIXTURE_LINKS: list[tuple[str, str]] = [
    ("Inici", "https://example.test/"),
    ("Contacte", "https://example.test/contacte"),
]


@pytest.fixture()
def db_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(db_seed, "COMPANY_INFO", FIXTURE_COMPANY_INFO)
    monkeypatch.setattr(db_seed, "TEAM_MEMBERS", FIXTURE_TEAM_MEMBERS)
    monkeypatch.setattr(db_seed, "SERVICES", FIXTURE_SERVICES)
    monkeypatch.setattr(db_seed, "ROUTING_RULES", FIXTURE_ROUTING_RULES)
    monkeypatch.setattr(db_seed, "FAQ", FIXTURE_FAQ)
    monkeypatch.setattr(db_seed, "LINKS", FIXTURE_LINKS)
    path = tmp_path / "caravista.db"
    db.init_db(path)
    return path


def test_init_db_creates_all_tables(db_path: Path) -> None:
    con = sqlite3.connect(db_path)
    try:
        names = {
            row[0]
            for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    finally:
        con.close()
    assert set(TABLES) <= names


def test_init_db_is_idempotent(db_path: Path) -> None:
    db.init_db(db_path)
    con = sqlite3.connect(db_path)
    try:
        counts = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in TABLES}
    finally:
        con.close()
    assert counts == {
        "company_info": len(FIXTURE_COMPANY_INFO),
        "team_members": len(FIXTURE_TEAM_MEMBERS),
        "services": len(FIXTURE_SERVICES),
        "routing_rules": len(FIXTURE_ROUTING_RULES),
        "faq": len(FIXTURE_FAQ),
        "links": len(FIXTURE_LINKS),
    }


def test_init_db_with_empty_seed_creates_empty_tables(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The shipped placeholder seed (all empty) must still build a usable DB.

    This is the state the repo is in until Caravista's facts land, so startup
    must not depend on any table having rows.
    """
    monkeypatch.setattr(db_seed, "COMPANY_INFO", {})
    for name in ("TEAM_MEMBERS", "SERVICES", "ROUTING_RULES", "FAQ", "LINKS"):
        monkeypatch.setattr(db_seed, name, [])
    path = tmp_path / "empty.db"
    db.init_db(path)
    assert db.get_company_info(path=path) == []
    assert db.list_services(path=path) == []
    assert db.search_team("qualsevol", path=path) == []


def test_get_company_info_all(db_path: Path) -> None:
    rows = db.get_company_info(path=db_path)
    assert len(rows) == len(FIXTURE_COMPANY_INFO)
    assert {"key", "value"} <= set(rows[0])


def test_get_company_info_selected_keys(db_path: Path) -> None:
    rows = db.get_company_info(["phone_main", "location"], path=db_path)
    assert {r["key"]: r["value"] for r in rows} == {
        "phone_main": "900 000 000",
        "location": "Vilafixture",
    }


def test_get_company_info_miss(db_path: Path) -> None:
    assert db.get_company_info(["no_such_key"], path=db_path) == []


def test_get_company_info_empty_keys(db_path: Path) -> None:
    # Relies on SQLite accepting an empty IN () list — lock that in.
    assert db.get_company_info([], path=db_path) == []


def test_search_team_by_name(db_path: Path) -> None:
    rows = db.search_team("corella", path=db_path)
    names = {r["name"] for r in rows}
    assert {"Mar Corella", "Pau Corella"} <= names
    assert {"id", "name", "role", "department"} <= set(rows[0])


def test_search_team_by_department(db_path: Path) -> None:
    rows = db.search_team("LABORAL", path=db_path)
    assert rows and all(r["department"] == "Laboral" for r in rows)


def test_search_team_full_sentence_matches_department(db_path: Path) -> None:
    rows = db.search_team("qui porta el departament laboral?", path=db_path)
    assert rows and all(r["department"] == "Laboral" for r in rows)


def test_search_team_full_sentence_matches_name(db_path: Path) -> None:
    rows = db.search_team("En què treballa l'Ona Vidal?", path=db_path)
    assert [r["name"] for r in rows] == ["Ona Vidal"]


def test_search_team_by_role_substring(db_path: Path) -> None:
    rows = db.search_team("administradora de finques", path=db_path)
    assert [r["name"] for r in rows] == ["Núria Exemple"]


def test_search_team_role_words_with_prefix_in_field(db_path: Path) -> None:
    # role is "Tècnica · Administradora de finques" — neither string contains
    # the other whole, so word-level overlap is required.
    rows = db.search_team("Qui és administradora de finques?", path=db_path)
    assert "Núria Exemple" in {r["name"] for r in rows}


def test_search_team_first_name_only(db_path: Path) -> None:
    rows = db.search_team("Hi ha alguna Núria a l'equip?", path=db_path)
    assert "Núria Exemple" in {r["name"] for r in rows}


def test_search_team_accent_insensitive(db_path: Path) -> None:
    # Users often type without accents: "Nuria" must find "Núria Exemple" and
    # "juridic" the "Jurídic" department.
    rows = db.search_team("qui es la nuria?", path=db_path)
    assert "Núria Exemple" in {r["name"] for r in rows}
    rows = db.search_team("qui porta el departament juridic?", path=db_path)
    assert rows and all(r["department"] == "Jurídic" for r in rows)


def test_search_team_miss(db_path: Path) -> None:
    assert db.search_team("nobody-here", path=db_path) == []


def test_search_team_blank_returns_nothing(db_path: Path) -> None:
    assert db.search_team("   ", path=db_path) == []


def test_list_services(db_path: Path) -> None:
    rows = db.list_services(path=db_path)
    assert len(rows) == len(FIXTURE_SERVICES)
    assert {"id", "area_key", "name", "one_liner", "url"} <= set(rows[0])


def test_search_faq_hit(db_path: Path) -> None:
    rows = db.search_faq("horari", path=db_path)
    assert rows and all("horari" in r["question"].lower() for r in rows)
    assert {"id", "question", "answer"} <= set(rows[0])


def test_search_faq_paraphrase_matches(db_path: Path) -> None:
    rows = db.search_faq("Com puc deixar una ressenya de Google?", path=db_path)
    assert [r["question"] for r in rows] == ["Com puc deixar/veure ressenyes?"]


def test_search_faq_filler_words_alone_do_not_match(db_path: Path) -> None:
    # Shares only interrogative scaffolding ("Com puc") with stored questions —
    # the overlap heuristic must not fire on filler words.
    assert db.search_faq("Com puc pagar una factura?", path=db_path) == []


def test_search_faq_miss(db_path: Path) -> None:
    assert db.search_faq("zzz-no-match", path=db_path) == []


def test_search_faq_blank_returns_nothing(db_path: Path) -> None:
    assert db.search_faq("   ", path=db_path) == []


def test_match_routing_rule_phrase_in_text(db_path: Path) -> None:
    rows = db.match_routing_rule("Hola, vull contractar personal aviat", path=db_path)
    assert any(r["area"] == "Laboral" for r in rows)
    assert {"id", "trigger_examples", "area", "bot_action"} <= set(rows[0])


def test_match_routing_rule_text_in_phrase(db_path: Path) -> None:
    rows = db.match_routing_rule("renda / irpf", path=db_path)
    assert rows


def test_match_routing_rule_paraphrased_trigger(db_path: Path) -> None:
    rows = db.match_routing_rule(
        "vull constituir una societat, amb qui he de parlar?", path=db_path
    )
    assert any(r["area"] == "Jurídic" for r in rows)


def test_match_routing_rule_shared_filler_word_does_not_match(db_path: Path) -> None:
    # "vull" appears in several trigger phrases; one shared word out of many
    # must stay below the half-overlap threshold.
    assert db.match_routing_rule("vull informació general", path=db_path) == []


def test_match_routing_rule_miss(db_path: Path) -> None:
    assert db.match_routing_rule("qqqqq", path=db_path) == []


def test_match_routing_rule_blank_text_matches_nothing(db_path: Path) -> None:
    assert db.match_routing_rule("", path=db_path) == []
    assert db.match_routing_rule("   ", path=db_path) == []


def test_list_links(db_path: Path) -> None:
    rows = db.list_links(path=db_path)
    assert len(rows) == len(FIXTURE_LINKS)
    assert {"id", "label", "url"} <= set(rows[0])
