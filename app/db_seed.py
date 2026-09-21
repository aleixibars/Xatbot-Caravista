"""Structured seed data for the Caravista knowledge base.

Pure data, no DB/SQL here — ``app/db.py`` creates the SQLite schema and loads
these constants into it. Keeping the data as plain Python literals means the
schema-building code has a single, unambiguous source to load from instead of
re-deriving it from prose.

**These constants are empty placeholders.** The client's structured facts
(contact details, team, services, routing table, FAQ) are filled in by the
"seed Caravista structured facts" issue once the source material exists; the
narrative half of the knowledge base is ingested into Qdrant from
``knowledge/`` (see ``app/ingest.py``). Until then the router's SQL lookups
find nothing and every question falls through to the vector search, which is
the intended fallback (see ``app/rag.py``).

Shapes are load-bearing — ``app/db.py`` unpacks each tuple positionally into
its INSERT statement, so a row must keep exactly the fields documented above
each constant.
"""

from __future__ import annotations

# Flat company facts — one row per key in SQLite (company_info(key, value)).
# Keys consumed elsewhere in the app: `phone_main`, `whatsapp`,
# `hours_mon_thu`, `hours_fri` are appended to every answer's CONTEXT by
# `rag._contact_context()` so the chat model never invents contact details.
COMPANY_INFO: dict[str, str] = {}

# (name, role, department)
TEAM_MEMBERS: list[tuple[str, str, str]] = []

# (area_key, name, one_liner, url)
SERVICES: list[tuple[str, str, str, str]] = []

# (trigger_examples, area, bot_action)
# `trigger_examples` is a single comma-separated string — `db.match_routing_rule`
# splits it on commas and matches each phrase against the question.
ROUTING_RULES: list[tuple[str, str, str]] = []

# (question, answer)
FAQ: list[tuple[str, str]] = []

# (label, url)
LINKS: list[tuple[str, str]] = []
