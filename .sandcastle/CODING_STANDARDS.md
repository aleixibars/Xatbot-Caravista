# Coding Standards

Loaded by the implementer and reviewer agents via `.sandcastle/CODING_STANDARDS.md`.

## Product

RAG chatbot for a tax consultancy's clients. Answers questions about general tax regulation using
only content retrieved from the knowledge base — never invents advice, and closes advice-adjacent
answers with a disclaimer directing the user to a human advisor (see `CONTEXT.md`, issue #49). See `CONTEXT.md` for the full domain model and
`docs/adr/` for the decisions behind the stack below.

## Stack

- **Backend:** Python 3.12, Flask, served by gunicorn (`--workers 1 --threads 8`, single worker
  because conversation history lives in the process — see ADR-0002).
- **Vector DB:** Qdrant Cloud (managed, free tier for this PoC).
- **Embeddings:** OpenAI `text-embedding-3-small` (1536 dims) — see ADR-0001.
- **Chat model:** DeepSeek `deepseek-chat` (V4-Flash) via its OpenAI-compatible API — see
  ADR-0001.
- **Frontend:** one static HTML/CSS/JS page (no framework, no build step) served by Flask, calling
  `/api/chat`.
- **Layout:** single Python app at the repo root (`app/`), no monorepo, no JS workspaces. The root
  `package.json` exists only to run the `.sandcastle/agent-workflows/` agent tooling — it is not
  the product.
- **Deploy:** Render Web Service (Docker), auto-deploy on push to `main`. See `render.yaml`.

## Style

- Python, type hints everywhere, checked with `mypy --ignore-missing-imports`.
- `ruff` for linting (`ruff check .`) — no unused imports, no dead code left "for later".
- snake_case for functions/variables, PascalCase for classes.
- Config (env vars) read once at startup in `app/config.py`; fail fast (raise / exit) if a
  required var is missing. Never hardcode secrets or default API keys in code.
- Keep `app/rag.py` (embed/search/answer) free of Flask — it must be callable and testable without
  an HTTP request.

## Testing

- `pytest` for unit tests. Mock the OpenAI/DeepSeek/Qdrant clients — tests never call the real
  APIs (no network, no cost, no API keys required in CI).
- Red-green-refactor where a test seam already exists or is being introduced for this change.
- Do not invent new test seams (e.g. extracting a function purely so it can be unit-tested) — this
  produces spaghetti tests. Test through the existing public interface (`app/rag.py` functions,
  the `/api/chat` route).
- Run `npm run typecheck` and `npm run test` before every commit (these shell out to
  `ruff`/`mypy`/`pytest` — see root `package.json`). Run focused tests for the area touched.

## Architecture

- Keep modules focused on a single responsibility: `app/config.py` (env), `app/rag.py`
  (embed/search/answer), `app/web.py` (Flask routes only, thin — no business logic inline), `app/
  ingest.py` (knowledge-base ingestion, run offline/manually, not exposed over HTTP for this PoC).
- Every advice-adjacent answer (`routing_rules`/`faq`/`rag` labels and the no-context fallback)
  must end with the fixed disclaimer defined in `CONTEXT.md` — never let the model present an
  answer as final tax advice. Pure-fact labels skip it (issue #49).
- Never commit real secrets — `.env.example` only; real values live in Render env vars and GitHub
  Actions secrets.
