# ADR-0002: Access, knowledge-base scope, legal posture, history, and hosting

## Status

Accepted (2026-08-24, PoC grill session).

## Context

Product is a client-facing chatbot for a tax consultancy, PoC stage. Several independent scoping
decisions were needed before implementation could start: who can use it, what it's allowed to
know, what it's allowed to say, where conversation state lives, and where it runs.

## Decisions

- **Access:** open, no login. Simplest for a PoC; revisit if/when the product needs per-client
  data or abuse becomes a problem.
- **Knowledge-base scope:** general tax regulation only (legislation, guides, FAQs). No
  client-specific documents or personal data go into Qdrant for this PoC — sidesteps the need for
  per-client payload filtering and most GDPR concerns on the KB side. (User-typed messages may
  still contain personal info incidentally — see logging below.)
- **Legal posture:** informative only. Every answer is grounded strictly in retrieved context, and
  the bot never presents an answer as final, actionable tax advice. Originally the fixed
  disclaimer (directing the user to confirm with a human advisor) was attached to every answer;
  refined for issue #49: it's appended only where the content could plausibly resemble
  guidance — the `routing_rules`, `faq` and `rag` router labels (escalation guidance, audit
  thresholds, narrative content) and the no-context fallback (which points at a human anyway).
  Pure-fact labels (`company_info`, `team_members`, `services` — hours, people, service list)
  skip it: there's no advice there, only noise from repeating the caveat.
- **History storage:** in-process memory (`{session_id: [...]}` dict), gunicorn run with
  `--workers 1` so the memory is actually shared across requests for a session. Lost on
  restart/redeploy — acceptable for a PoC; moving to Redis/a DB is a follow-up if history needs to
  survive deploys.
- **Conversation logging:** each exchange (question + answer, no other metadata) written as a
  JSONL line to stdout. Render captures process stdout in its log dashboard, so this needs no
  extra infrastructure (no log file, no DB) while still letting the team review what people asked
  during the PoC.
- **Vector DB hosting:** Qdrant Cloud, free tier. Avoids self-hosting a container with a persistent
  disk on Render just for a PoC.
- **App hosting:** Render Web Service (Docker image), auto-deploy on push to `main` — consistent
  with the rest of the agent pipeline (fase 6 of the overall plan).

## Consequences

- No auth means no per-user rate limiting is possible by identity; a basic per-IP limit is still
  worth adding (tracked as a separate issue) since the chat endpoint costs money per call.
- Because the KB has no client data, there's no filter-by-client logic anywhere in `app/rag.py` —
  if the product later needs client-specific answers, that's a new decision (new ADR), not a
  small patch.
- Qdrant Cloud's free tier has a storage/throughput ceiling — fine for a PoC-sized knowledge base;
  revisit if the real knowledge base outgrows it.
