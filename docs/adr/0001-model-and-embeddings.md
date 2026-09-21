# ADR-0001: Chat model, embedding model, and repo layout

## Status

Accepted (2026-08-24, PoC grill session).

> **Temporary override (2026-08-24, issue #21 — reverted 2026-08-25, issue #35):** while the
> DeepSeek account was out of balance, chat temporarily ran on OpenAI `gpt-4.1-nano`. The balance
> was topped up and `deepseek-chat` restored per the decision below.

## Context

Needed a chat model and embedding model for a RAG chatbot, optimizing for low cost since this is a
PoC with no revenue yet, while keeping answer quality acceptable for tax-related questions.

Priced (Aug 2026):
- Embeddings: `text-embedding-3-small` $0.02/M tokens vs `text-embedding-3-large` $0.13/M tokens
  (6.5x), 1536 vs 3072 dims.
- Chat: DeepSeek `deepseek-chat` (V4-Flash) ~$0.14/$0.28 per M (input/output), OpenAI
  `gpt-4o-mini` $0.15/$0.60 per M, Claude Haiku $0.80/$4.00 per M.

Also needed to decide repo layout: the agent pipeline (`.sandcastle/`, `package.json`) was copied
from a prior Node/TypeScript project's template, but this product is Python.

## Decision

- **Embeddings:** `text-embedding-3-small` (OpenAI), 1536 dims. The RAG design only needs
  fragments to be *findable*, not maximally precise — the model still answers from the retrieved
  text, so the smaller embedding's practical quality loss is not worth 6.5x the cost.
- **Chat:** DeepSeek `deepseek-chat`, called through its OpenAI-compatible `/chat/completions` API
  (separate `DEEPSEEK_API_KEY`, `base_url=https://api.deepseek.com`). Chosen explicitly for lowest
  cost per the user's request. Because the answer is grounded in retrieved context (RAG), the
  model's job is closer to "summarize this text for the question" than "reason from scratch" —
  lowering the bar where instruction-following differences between providers matter most.
- **Repo layout:** the product is a single Python app at `app/` (Flask + gunicorn). The root
  `package.json` stays, but only to run `.sandcastle/agent-workflows/` (which needs Node/tsx) — it
  is not the product's dependency manifest. `requirements.txt` is.

## Consequences

- Two API keys in play for the LLM side (`OPENAI_API_KEY` for embeddings, `DEEPSEEK_API_KEY` for
  chat), plus `QDRANT_API_KEY`. All three fail-fast at startup if missing (`app/config.py`).
- If DeepSeek's answer quality proves insufficient in testing, swapping to `gpt-4o-mini` is a
  one-file change (`app/rag.py`'s client construction) — the `/chat/completions`-shaped call stays
  the same either way.
- Follow-up note (non-goal for now, tracked here so it isn't lost): if the PoC graduates and needs
  source citations, the `source` field already carried in each Qdrant payload point is there for
  that — no re-ingestion needed to add it later.
