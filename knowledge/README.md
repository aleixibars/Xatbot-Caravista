# Knowledge base sources

Drop Caravista's source documents here (`.md`, `.txt`, `.pdf`, `.docx`), then ingest them:

```bash
python -m app.ingest knowledge/
```

Ingestion chunks each document into fragments, embeds them with
`text-embedding-3-small` and upserts them into the Qdrant collection named by
`QDRANT_COLLECTION` (`caravista`). Point ids are derived from the file name plus the chunk
index, so re-running ingestion after editing a document overwrites its fragments instead of
duplicating them — but **renaming a file orphans its old fragments**, which then have to be
deleted from Qdrant by hand.

Two halves, one source (see ADR-0003):

- **Narrative prose** — history, how the service works, tone — belongs here, in Markdown with
  `##` headings. Headings start a new fragment, so keep each section about one thing.
- **Structured facts** — contact details, team, services, routing table, FAQ — do **not** belong
  here. They go into `app/db_seed.py` as plain Python literals and are served from SQLite, which
  answers them exactly instead of approximately.

Do not put customer-specific or personal data in this directory (ADR-0002): the knowledge base is
public-facing content only.

This directory is currently empty of sources — the client's material has not been supplied yet.
