# Context: Caravista chatbot

Single-context repo (see `docs/agents/domain.md` for how agents should use this file).

## What this is

A retrieve-and-generate (RAG) chatbot for **Caravista**'s customers. A visitor asks a question
in chat; the service retrieves the most relevant fragments of Caravista's knowledge base from
Qdrant and asks the chat model to answer using only that context. The web page is deliberately
shaped like a WhatsApp conversation because the WhatsApp Cloud API channel (`app/whatsapp.py`)
is where this bot is headed — the web widget is a rehearsal of that surface, not a separate
product.

This repo is a replica of the `Reviu-Agent` chatbot (same architecture, same agent pipeline,
same deploy shape), re-pointed at a different client.

## Status of the knowledge base

**Empty, on purpose.** The client's content has not been supplied yet:

- `app/db_seed.py` — every seed constant is an empty placeholder.
- `knowledge/` — holds no source documents.

Until they are filled in, the router's SQL lookups find nothing and every question falls through
to the vector search, which finds nothing either, so the bot answers with `NO_CONTEXT_MESSAGE`.
That is the intended behaviour of an unfed bot, not a bug. See the "Caravista knowledge base"
issues.

## Glossary

- **Fragment** — a chunk of knowledge-base text (~200–500 tokens), the unit stored in Qdrant and
  retrieved at query time. One Qdrant point = one fragment. See ADR-0001 for the embedding it's
  stored with.
- **Knowledge base** — the Caravista content ingested into Qdrant, plus the structured facts in
  SQLite. Contains **no customer-specific data** (no customer documents, no personal records) —
  see ADR-0002.
- **Session** — one visitor's conversation, identified by a `session_id` the backend hands back on
  first contact and the frontend echoes on every request. History for a session lives in the
  Flask process's memory only (see ADR-0002) — lost on restart/redeploy, acceptable for a PoC.
- **Disclaimer** — the fixed sentence appended to answers that border on a commitment to the
  customer, stating the response is general information and the user should confirm with the
  team. Appended for the `routing_rules`/`faq`/`rag` router labels and the no-context fallback (a
  fact-label lookup that matches no rows falls through to the vector search and counts as `rag`);
  skipped for pure-fact labels (`company_info`, `team_members`, `services`) where it's noise.
  Exact wording lives in `app/rag.py` (`DISCLAIMER` constant) so it's changed in one place.
- **Ingestion** — the offline step (`app/ingest.py`, run manually, not an HTTP endpoint) that
  parses source documents (pdf/docx/txt/md), chunks them into fragments, embeds them, and upserts
  them into Qdrant with a stable id (so re-running ingestion overwrites rather than duplicates).

## Decisions (summary — full rationale in `docs/adr/`)

| Decision | Choice | ADR |
| --- | --- | --- |
| Access | Open, no login | ADR-0002 |
| Knowledge base scope | Caravista's own public/business content, no customer data | ADR-0002 |
| Chat model | DeepSeek `deepseek-chat` (V4-Flash) | ADR-0001 |
| Embedding model | OpenAI `text-embedding-3-small`, 1536 dims | ADR-0001 |
| Legal posture | Informative only; disclaimer on commitment-adjacent answers (`routing_rules`/`faq`/`rag` labels + no-context fallback), skipped for pure-fact labels | ADR-0002 |
| History storage | In-process memory, 1 gunicorn worker | ADR-0002 |
| Conversation logging | stdout JSONL (captured by Render's log dashboard, no extra infra) | ADR-0002 |
| Vector DB hosting | Qdrant Cloud, free tier — collection `caravista` on the existing cluster | ADR-0002 |
| Repo layout | Python app at root (`app/`); `package.json` is agent tooling only | ADR-0001 |
| Retrieval | Hybrid: SQLite for structured facts, Qdrant RAG for narrative — a router picks per question | ADR-0003 |
| Frontend | WhatsApp-shaped web chat, no framework, no build step | ADR-0004 |

## Client

**Caravista** — client details pending. When the material arrives, the structured facts (contact,
team, services, routing table, FAQ) go into `app/db_seed.py` for SQLite and the narrative
sections into `knowledge/` for Qdrant ingestion. See ADR-0003 for why the split exists.

## Non-goals (for this PoC)

- No authentication, no per-customer data isolation.
- No citation/source display beyond what's in `docs/adr/0001-model-and-embeddings.md`'s
  follow-up note.
- No persistent conversation storage (DB) — stdout logging only.
- No CI/CD beyond the existing agent pipeline + Render auto-deploy.
