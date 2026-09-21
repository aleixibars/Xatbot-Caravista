# ADR-0003: Hybrid SQL + RAG retrieval with a router

## Status

Accepted (2026-08-24).

## Context

Real knowledge base arrived: `knowledge/` (the client's own content) for **Caravista
Assessors** (Lleida tax/labour/legal consultancy — this PoC's actual client, see
`app/db_seed.py`/`CONTEXT.md`). Unlike ADR-0002's generic-regulation assumption, this document
mixes two shapes of content:

- **Structured facts**: contact info, opening hours, the 14-person team roster, the 8 service
  areas (short form), the intent→department routing table, the FAQ, the resource links. All
  naturally rows in tables — the exact strings must come back unmodified (a phone number or an
  address is not something to let an LLM paraphrase from a fuzzy vector match).
- **Unstructured narrative**: the long per-service descriptions (§4), the escalation policy prose
  (§8), positioning/tone guidance (§1). Good RAG fragment material — chunked as before via
  `app/ingest.py`.

## Decision

- **SQLite** for the structured half, `data/caravista.db`, built inside the Docker image from
  `app/db_seed.py` (plain Python literals, extracted once from the source doc — see that file).
  No extra managed DB service: the data is small, static, and read-only at request time, and the
  service already runs a single gunicorn worker (ADR-0002), so a bundled SQLite file has no
  concurrency downside here.
- **Router**: before retrieving, one cheap DeepSeek call classifies the question as `sql` or
  `rag` (plus, for `sql`, which table it most likely answers from: `company_info`, `team_members`,
  `services`, `routing_rules`, or `faq`). `sql` queries the matching table; if that returns no row,
  fall through to the existing vector search rather than answering empty. `rag` goes straight to
  `app.rag.search` as today.
- The narrative sections of the `knowledge/` documents still get chunked and ingested into Qdrant
  via `app/ingest.py` (no change to that tool) — the router's `rag` branch is the same retrieval
  path as ADR-0001/0002, just no longer the only path.

## Consequences

- Two lookups can happen per user turn (router call + the sql-or-rag lookup) instead of one — an
  extra cheap DeepSeek call per question. Acceptable at PoC volume; revisit if a heuristic
  (keyword match against `faq.question`/`routing_rules.trigger_examples`) is worth adding later to
  skip the router call for obvious matches.
- `app/db_seed.py` is the single source of truth for the structured data — re-extracting it from
  the markdown by hand a second time would drift; edit the seed, rebuild the DB.
- Team member emails are deliberately **not** in `TEAM_MEMBERS` — the source doc explicitly says
  the bot must not hand out individual emails over WhatsApp (§5). Don't add them later without
  revisiting that constraint.
