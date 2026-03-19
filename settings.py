"""
settings.py — single source of truth for all runtime configuration.

Reads from .env on import. All other modules must go through the
functions here rather than calling os.getenv directly.
"""

import os
from pathlib import Path

from dotenv import load_dotenv, set_key

_ENV_PATH = Path(__file__).parent / ".env"
_KEY_VAULT_DIR = "DOCS_DIR"
_KEY_API_KEY = "OPENAI_API_KEY"

load_dotenv()


def vault_dir() -> str:
    return os.getenv(_KEY_VAULT_DIR, "")


def api_key() -> str:
    return os.getenv(_KEY_API_KEY, "")


def is_configured() -> bool:
    return bool(vault_dir()) and bool(api_key())


def save(vault_path: str, openai_api_key: str) -> None:
    """Persist config to .env and update the running process environment."""
    _ENV_PATH.touch()
    set_key(str(_ENV_PATH), _KEY_VAULT_DIR, vault_path)
    set_key(str(_ENV_PATH), _KEY_API_KEY, openai_api_key)
    os.environ[_KEY_VAULT_DIR] = vault_path
    os.environ[_KEY_API_KEY] = openai_api_key
