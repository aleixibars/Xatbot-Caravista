# ADR-0004: WhatsApp-shaped web frontend

## Status

Accepted (2026-09-21, part of the Caravista replication).

## Context

This bot's destination is the WhatsApp Cloud API channel (`app/whatsapp.py`,
`README_WHATSAPP.md`) — that is where Caravista's customers will actually talk to it. The web
page exists to demo and rehearse that channel for the client while the WhatsApp side is being
wired up, not to be a separate product surface with its own design language. A generic
chat-widget look would demo a product that isn't the one being built.

## Decision

- The web chat **replicates WhatsApp's conversation UI**: header with avatar and presence line,
  doodle wallpaper, tailed bubbles with timestamps and delivery ticks, a typing indicator while
  the bot works, an Enter-to-send composer, and WhatsApp's own light and dark palettes
  (`prefers-color-scheme`). Inline formatting follows WhatsApp's rules (`*bold*`, `_italic_`,
  `~strikethrough~`), the same conventions the WhatsApp channel renders.
- It is built as **plain HTML/CSS/JS** (`app/static/index.html`, `styles.css`, `app.js`) served
  directly by Flask — no framework, no build step, no `node_modules` in the product (the root
  `package.json` is agent tooling only, see ADR-0001).
- One deliberate divergence from the WhatsApp channel: the disclaimer (ADR-0002, issue #49) is
  **split out of the answer bubble into a small caption** under it. The backend appends it after
  a `\n\n---\n` separator; `app.js` splits on that separator and renders the tail as
  `bubble__disclaimer`. On WhatsApp the disclaimer stays inline in the message body — the web
  page can afford the visual separation, and it keeps the caveat legible without burying the
  answer.

## Consequences

- The client recognises the product immediately — the demo looks like the thing they asked for,
  not a placeholder widget.
- Zero build tooling: no bundler, no transpiler, no frontend dependency updates. The page is
  three static files Flask already serves.
- The visual conventions are **copied, not designed**: when changing the UI, check against real
  WhatsApp rather than arguing from taste. If WhatsApp's look drifts, ours is allowed to drift
  with it.
- Hand-written DOM code instead of components — acceptable at this size, but the page should stay
  a single conversation view; if it grows real product features, revisit this ADR before reaching
  for a framework.
- The look imitates a familiar product, so the page must stay clearly branded as **Caravista's
  assistant** (its own name, avatar and title) and must never present itself as WhatsApp or as
  affiliated with Meta.
