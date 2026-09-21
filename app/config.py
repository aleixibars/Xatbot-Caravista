"""Configuration read once at import time.

Required env vars fail fast (raise ``RuntimeError``) if missing, per the coding
standards. Model/dimension choices are constants (not env vars) — see ADR-0001.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


# Required secrets / connection settings.
OPENAI_API_KEY: str = _require("OPENAI_API_KEY")
DEEPSEEK_API_KEY: str = _require("DEEPSEEK_API_KEY")
QDRANT_URL: str = _require("QDRANT_URL")
QDRANT_API_KEY: str = _require("QDRANT_API_KEY")

# Optional, with a default.
QDRANT_COLLECTION: str = os.environ.get("QDRANT_COLLECTION", "caravista")
DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"

# Meta WhatsApp Cloud API — deliberately NOT `_require`d: the web
# app must keep booting (/, /health, /api/chat) without WhatsApp set up;
# /webhook itself errors clearly when these are missing.
META_ACCESS_TOKEN: str | None = os.environ.get("META_ACCESS_TOKEN")
META_PHONE_NUMBER_ID: str | None = os.environ.get("META_PHONE_NUMBER_ID")
META_VERIFY_TOKEN: str | None = os.environ.get("META_VERIFY_TOKEN")
META_APP_SECRET: str | None = os.environ.get("META_APP_SECRET")
# Local testing only — never default to true.
SKIP_SIGNATURE_VALIDATION: bool = (
    os.environ.get("SKIP_SIGNATURE_VALIDATION", "false").lower() == "true"
)

# Fixed choices — see ADR-0001.
EMBED_MODEL: str = "text-embedding-3-small"
CHAT_MODEL: str = "deepseek-chat"
EMBED_DIMS: int = 1536
