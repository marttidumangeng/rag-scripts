"""Load IMPORT_SYNC_* and related vars from robotaigeek-server/.env (one-time setup)."""

from __future__ import annotations

import os
from pathlib import Path

_SERVER_DIR = Path(__file__).resolve().parents[2] / "robotaigeek-server"
_LOADED = False

# Sensible local default when developing against `runserver` on the same machine.
_DEFAULT_LOCAL_API_BASE = "http://127.0.0.1:8000/api/v1/"


def load_research_env(*, local: bool = False) -> None:
    """Load robotaigeek-server/.env then .env.local (local overrides). Idempotent.

    If ``local=True`` (or the env var ``RESEARCH_USE_LOCAL=1`` is set), the
    ``*_LOCAL`` variants of the API vars are copied into the canonical names so
    that all scripts target the local dev server without touching the .env file:

        IMPORT_SYNC_API_BASE_URL_LOCAL  → IMPORT_SYNC_API_BASE_URL
        IMPORT_SYNC_API_KEY_LOCAL       → IMPORT_SYNC_API_KEY
        RESEARCH_CREATED_BY_ID_LOCAL    → RESEARCH_CREATED_BY_ID
    """
    global _LOADED
    if _LOADED:
        return

    try:
        from dotenv import load_dotenv
    except ImportError:
        _apply_defaults(local=local)
        _LOADED = True
        return

    env_file = _SERVER_DIR / ".env"
    if env_file.is_file():
        load_dotenv(env_file)

    local_env = _SERVER_DIR / ".env.local"
    if local_env.is_file():
        load_dotenv(local_env, override=True)

    _apply_defaults(local=local)
    _LOADED = True


def _apply_defaults(*, local: bool = False) -> None:
    use_local = local or os.environ.get("RESEARCH_USE_LOCAL", "").lower() in ("1", "true", "yes")
    if use_local:
        _copy_local_vars()
    if not os.environ.get("IMPORT_SYNC_API_BASE_URL", "").strip():
        os.environ["IMPORT_SYNC_API_BASE_URL"] = _DEFAULT_LOCAL_API_BASE


def _copy_local_vars() -> None:
    """Copy *_LOCAL env var variants into the canonical names used by all scripts."""
    mapping = {
        "IMPORT_SYNC_API_BASE_URL_LOCAL": "IMPORT_SYNC_API_BASE_URL",
        "IMPORT_SYNC_API_KEY_LOCAL": "IMPORT_SYNC_API_KEY",
        "RESEARCH_CREATED_BY_ID_LOCAL": "RESEARCH_CREATED_BY_ID",
    }
    for src, dst in mapping.items():
        val = os.environ.get(src, "").strip()
        if val:
            os.environ[dst] = val
