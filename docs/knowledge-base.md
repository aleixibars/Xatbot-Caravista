# Working on the knowledge base

The client's source documents live in `knowledge/` (`.md`, `.txt`, `.pdf`, `.docx`). After
editing or adding one, re-ingest:

```bash
python -m app.ingest knowledge/
```

Ingestion chunks each document into fragments, embeds them with `text-embedding-3-small` and
upserts them into the Qdrant collection named by `QDRANT_COLLECTION` (`caravista`). Point ids are
derived from the file name plus the chunk index, so re-running ingestion after editing a document
overwrites its fragments instead of duplicating them — but **renaming or deleting a file orphans
its old fragments**, which then have to be deleted from Qdrant by hand. This file used to live in
`knowledge/` and was itself ingested as a fragment for exactly that reason: everything in that
directory is client content, and nothing else belongs there.

## The two halves (ADR-0003)

- **Narrative prose** — the carta dish by dish, the wine list, the chef's career, how the
  takeaway service works — belongs in `knowledge/`, in Markdown with `##` headings. A heading
  starts a new fragment, so keep each section about one thing.
- **Structured facts** — contact details, hours, the team, the service list, the routing table,
  the FAQ — do **not** belong there. They go into `app/db_seed.py` as plain Python literals and
  are served from SQLite, which answers them exactly instead of approximately.

Keep each fact on one side only. A fact present in both can be answered two different ways inside
a single response, because `rag.answer()` can put SQL rows and retrieved fragments in the same
CONTEXT.

## Rules

- Never invent a fact. Anything the source material does not state is left out, not guessed.
- No customer-specific or personal data (ADR-0002): the knowledge base is public-facing content
  only.
- Record the extraction date at the top of each document. Prices and menus change, and a reader
  needs to know how stale the answer may be.
