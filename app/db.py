"""SQLite layer for the structured half of ADR-0003 (hybrid SQL + RAG).

No Flask imports — callable and testable without an HTTP request, same rule as
``app/rag.py``. Schema is built from the plain literals in ``app/db_seed.py``
(the single source of truth); the DB file itself is generated, not committed.
"""

from __future__ import annotations

import re
import sqlite3
import unicodedata
from collections.abc import Sequence
from pathlib import Path

from app import db_seed

# Relative to the repo root locally and to /app in the Docker image (the CWD in
# both cases). init_db() creates the data/ directory if missing.
DB_PATH: Path = Path("data/caravista.db")

_SCHEMA: str = """
CREATE TABLE IF NOT EXISTS company_info (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS team_members (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    role TEXT NOT NULL,
    department TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS services (
    id INTEGER PRIMARY KEY,
    area_key TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    one_liner TEXT NOT NULL,
    url TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS routing_rules (
    id INTEGER PRIMARY KEY,
    trigger_examples TEXT NOT NULL,
    area TEXT NOT NULL,
    bot_action TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS faq (
    id INTEGER PRIMARY KEY,
    question TEXT NOT NULL,
    answer TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS links (
    id INTEGER PRIMARY KEY,
    label TEXT NOT NULL,
    url TEXT NOT NULL
);
"""

def _seeds() -> dict[str, tuple[str, Sequence[tuple[str, ...]]]]:
    """table -> (insert statement, seed rows), read from ``app/db_seed.py``.

    Built per call rather than once at import so the seed data stays a
    substitutable input: tests swap the ``db_seed`` constants for a small
    fixture dataset, which only works if this mapping is read after the swap.
    The client's real facts must never be a test dependency.
    """
    return {
        "company_info": (
            "INSERT INTO company_info (key, value) VALUES (?, ?)",
            list(db_seed.COMPANY_INFO.items()),
        ),
        "team_members": (
            "INSERT INTO team_members (name, role, department) VALUES (?, ?, ?)",
            db_seed.TEAM_MEMBERS,
        ),
        "services": (
            "INSERT INTO services (area_key, name, one_liner, url) VALUES (?, ?, ?, ?)",
            db_seed.SERVICES,
        ),
        "routing_rules": (
            "INSERT INTO routing_rules (trigger_examples, area, bot_action) VALUES (?, ?, ?)",
            db_seed.ROUTING_RULES,
        ),
        "faq": (
            "INSERT INTO faq (question, answer) VALUES (?, ?)",
            db_seed.FAQ,
        ),
        "links": (
            "INSERT INTO links (label, url) VALUES (?, ?)",
            db_seed.LINKS,
        ),
    }


def init_db(path: str | Path = DB_PATH) -> None:
    """Create the SQLite file/tables and seed each table only if it is empty.

    Idempotent — safe to call on every app startup. A table whose seed is
    empty (the current Caravista placeholder, see ``app/db_seed.py``) is
    created and left empty; the router then finds no rows and falls through
    to the vector search.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    try:
        con.executescript(_SCHEMA)
        for table, (insert_sql, rows) in _seeds().items():
            count = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            if count == 0:
                con.executemany(insert_sql, rows)
        con.commit()
    finally:
        con.close()


# Short fixed stoplist of very common Catalan words, so the keyword-overlap
# heuristic below never matches on filler words alone. Deliberately not a
# library / real NLP — this is enough for the seed data's phrasing.
_STOPWORDS: frozenset[str] = frozenset(
    {"de", "el", "la", "i", "a", "un", "una", "amb", "per"}
)


def _fold(text: str) -> str:
    """Lower-case and strip accents, so "nuria" equals "Núria".

    Users routinely type without accents; folding both the stored field and
    the question keeps the word comparison symmetric.
    """
    decomposed = unicodedata.normalize("NFD", text.lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def _significant_words(text: str) -> list[str]:
    """Folded words of ``text`` minus the stoplist and single letters."""
    return [
        w for w in re.findall(r"\w+", _fold(text)) if len(w) > 1 and w not in _STOPWORDS
    ]


def _keyword_overlap(phrase: str, text_words: set[str]) -> bool:
    """True if at least half of ``phrase``'s significant words are in ``text_words``.

    Word overlap instead of a strict substring check because a paraphrase
    ("vull constituir una societat…") rarely contains a stored phrase
    ("constituir societat") contiguously, but it does reuse its key words.
    """
    words = _significant_words(phrase)
    if not words:
        return False
    hits = sum(1 for w in words if w in text_words)
    return hits * 2 >= len(words)


def _query(sql: str, params: tuple, path: str | Path) -> list[dict]:
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    try:
        return [dict(row) for row in con.execute(sql, params)]
    finally:
        con.close()


def get_company_info(
    keys: list[str] | None = None, *, path: str | Path = DB_PATH
) -> list[dict]:
    """All company_info rows, or only the given keys."""
    if keys is None:
        return _query("SELECT key, value FROM company_info", (), path)
    placeholders = ", ".join("?" for _ in keys)
    return _query(
        f"SELECT key, value FROM company_info WHERE key IN ({placeholders})",
        tuple(keys),
        path,
    )


def search_team(text: str, *, path: str | Path = DB_PATH) -> list[dict]:
    """Word-level match on name, role OR department (case- and accent-insensitive).

    Whole-field substring fails real questions: "Qui és administradora de
    finques?" contains neither the full role "Fiscal · Administradora de
    finques" nor vice versa, and "Núria" alone is only one word of the name
    "Núria Saez". A member matches when any significant word
    (:func:`_significant_words`) of a field appears among the question's words.
    """
    text_words = set(_significant_words(text))
    if not text_words:
        # Blank or all-filler input should be a miss, not a wildcard.
        return []
    rows = _query("SELECT id, name, role, department FROM team_members", (), path)
    matches = []
    for row in rows:
        fields = (row["name"], row["role"], row["department"])
        if any(w in text_words for f in fields for w in _significant_words(f)):
            matches.append(row)
    return matches


def list_services(*, path: str | Path = DB_PATH) -> list[dict]:
    return _query("SELECT id, area_key, name, one_liner, url FROM services", (), path)


def search_faq(text: str, *, path: str | Path = DB_PATH) -> list[dict]:
    """FAQ rows whose question matches ``text`` (case-insensitive).

    Bidirectional substring like :func:`search_team`, plus keyword overlap so
    a paraphrase ("Com puc deixar una ressenya de Google?") still finds the
    stored question ("Com puc deixar/veure ressenyes?").
    """
    needle = text.lower().strip()
    if not needle:
        # An empty needle is a substring of every question — that would match
        # every row, when blank input should be a miss.
        return []
    text_words = set(_significant_words(needle))
    rows = _query("SELECT id, question, answer FROM faq", (), path)
    matches = []
    for row in rows:
        question = row["question"].lower()
        if (
            question in needle
            or needle in question
            or _keyword_overlap(question, text_words)
        ):
            matches.append(row)
    return matches


def match_routing_rule(text: str, *, path: str | Path = DB_PATH) -> list[dict]:
    """Rules whose comma-separated trigger phrases overlap ``text``.

    A rule matches if any of its phrases is a substring of ``text`` or vice
    versa (case-insensitive), or shares enough significant words with it
    (:func:`_keyword_overlap`) — a paraphrase like "vull constituir una
    societat" never contains the phrase "constituir societat" contiguously.
    """
    needle = text.lower().strip()
    if not needle:
        # An empty needle is a substring of every phrase — that would match
        # every rule, when blank input should be a miss.
        return []
    text_words = set(_significant_words(needle))
    rows = _query(
        "SELECT id, trigger_examples, area, bot_action FROM routing_rules", (), path
    )
    matches = []
    for row in rows:
        phrases = [p.strip().lower() for p in row["trigger_examples"].split(",")]
        if any(
            p and (p in needle or needle in p or _keyword_overlap(p, text_words))
            for p in phrases
        ):
            matches.append(row)
    return matches


def list_links(*, path: str | Path = DB_PATH) -> list[dict]:
    return _query("SELECT id, label, url FROM links", (), path)
