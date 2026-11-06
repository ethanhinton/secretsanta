"""Environment-driven configuration.

Everything a deployer might want to tweak is read here, once at import:

  GMAIL_OAUTH_CLIENT_ID  OAuth client ID to identify this app to Google
                         ("Desktop app" type). Falls back to
                         ``DEFAULT_CLIENT_ID`` below.
  PORT                   Port the server listens on. Also used to build
                         the OAuth callback URL the user's browser lands
                         on after signing in — so the *published* host
                         port (Docker) must match this. Default 8000.
  SANTA_DATA_DIR         Directory holding ``state.json`` and
                         ``tokens.json``. Default: <project root>/data.
                         In Docker this is /data (mount a volume there).
"""
from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _data_dir() -> Path:
    raw = os.environ.get("SANTA_DATA_DIR", "").strip()
    if not raw:
        return PROJECT_ROOT / "data"
    p = Path(raw).expanduser()
    return p if p.is_absolute() else PROJECT_ROOT / p


DATA_DIR = _data_dir()
STATE_FILE = DATA_DIR / "state.json"
TOKENS_FILE = DATA_DIR / "tokens.json"

PORT = int(os.environ.get("PORT", "8000"))


# ---------------------------------------------------------------------------
# Default OAuth client ID (baked into the app / Docker image).
#
# A "Desktop app" client ID is a PUBLIC identifier — it carries no secret,
# so it is safe to ship. Paste YOUR client ID here (Google Cloud Console →
# APIs & Services → Credentials → your "Desktop app" client → Client ID).
# After that, end users need no Google setup at all: they click
# "Connect Gmail" and sign in with their own account.
#
# Deployers can override it per container with GMAIL_OAUTH_CLIENT_ID.
# ---------------------------------------------------------------------------
DEFAULT_CLIENT_ID = "REPLACE_WITH_YOUR_DESKTOP_CLIENT_ID"


def gmail_client_id() -> str:
    """The client ID to use: env var wins, else the bundled default."""
    env = os.environ.get("GMAIL_OAUTH_CLIENT_ID", "").strip()
    return env or DEFAULT_CLIENT_ID


def migrate_legacy_tokens() -> None:
    """One-off move of a pre-Docker ``tokens.json`` (project root → DATA_DIR)."""
    import shutil

    legacy = PROJECT_ROOT / "tokens.json"
    if legacy.exists() and not TOKENS_FILE.exists():
        TOKENS_FILE.parent.mkdir(parents=True, exist_ok=True)
        # shutil.move (not rename) so this also works across filesystems.
        shutil.move(str(legacy), str(TOKENS_FILE))
