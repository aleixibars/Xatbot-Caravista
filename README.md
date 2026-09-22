# Xatbot Caravista — RAG chatbot (PoC)

RAG chatbot answering questions about Caravista, grounded in a Qdrant knowledge base, with a
WhatsApp-shaped web chat in front of it. See [`CONTEXT.md`](./CONTEXT.md) for the domain model and
[`docs/adr/`](./docs/adr/) for the decisions behind the stack.

Architecture, agent pipeline and deploy shape are replicated from the `Reviu-Agent` repo; only the
client differs.

## Status

PoC, deployed and fed. The knowledge base was loaded on 2026-09-22 from
caravistarestaurant.com: structured facts in `app/db_seed.py`, narrative content in
`knowledge/caravista.md` (ingested into the Qdrant collection `caravista`). The WhatsApp channel
is the one part still switched off — the webhook exists, its `META_*` credentials do not.

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
- `.github/workflows/keep-alive.yml` — pings `/health` every 10 minutes so the free Render
  service does not spin down. Set the repo variable `HEALTH_URL` to
  `https://<service>.onrender.com/health` under Settings → Secrets and variables → Actions →
  Variables. GitHub disables scheduled workflows after 60 days without repository activity, so a
  silent stop means the schedule needs re-enabling under Actions.
- `render.yaml` — deploy blueprint (Render Web Service, Docker, auto-deploy on `main`).

## Checks

```bash
ruff check .
mypy app --ignore-missing-imports
pytest -q
```
