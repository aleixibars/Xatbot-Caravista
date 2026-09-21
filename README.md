# Xatbot Caravista — RAG chatbot (PoC)

RAG chatbot answering questions about Caravista, grounded in a Qdrant knowledge base, with a
WhatsApp-shaped web chat in front of it. See [`CONTEXT.md`](./CONTEXT.md) for the domain model and
[`docs/adr/`](./docs/adr/) for the decisions behind the stack.

Architecture, agent pipeline and deploy shape are replicated from the `Reviu-Agent` repo; only the
client differs.

## Status

PoC, **not yet fed**: `app/db_seed.py` and `knowledge/` are empty placeholders, so the bot answers
"no information found" until Caravista's content is supplied. Everything else — retrieval, router,
web chat, WhatsApp webhook, deploy — is in place.

Built by an autonomous agent pipeline — see `docs/agents/` and `.github/workflows/agent-*.yml`.
Work is tracked as GitHub issues; don't expect a hand-written implementation history.

## Local development

```bash
cp .env.example .env   # fill in the keys
python -m venv .venv && . .venv/Scripts/activate   # Windows; source .venv/bin/activate on Unix
pip install -r requirements.txt
python -m flask --app app.web run --debug
```

Then open <http://127.0.0.1:5000/>.

Ingest knowledge-base documents into Qdrant (offline step, not an HTTP endpoint):

```bash
python -m app.ingest knowledge/
```

## Repo layout

- `app/` — the Python product (Flask + gunicorn). See `.sandcastle/CODING_STANDARDS.md`.
  - `app/static/` — the WhatsApp-shaped chat page: plain HTML/CSS/JS, no framework, no build step.
  - `app/whatsapp.py` — the Meta WhatsApp Cloud API webhook (see `README_WHATSAPP.md`).
- `knowledge/` — knowledge-base source documents, ingested into Qdrant.
- `package.json` — **not** the product; only runs `.sandcastle/agent-workflows/` (the agent
  pipeline's own tooling, which needs Node/tsx).
- `.github/workflows/agent-*.yml` — the implement → review → merge → wave-advance pipeline.
- `render.yaml` — deploy blueprint (Render Web Service, Docker, auto-deploy on `main`).

## Checks

```bash
ruff check .
mypy app --ignore-missing-imports
pytest -q
```
