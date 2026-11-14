"""JSON persistence for app state.

Everything the app knows (participants, settings, the draw, send status)
lives in ``<DATA_DIR>/state.json`` (see ``config.py`` — ``SANTA_DATA_DIR``)
so an interrupted run or a failed send can be resumed later. Keep this file
private — it contains the full assignment.
"""
from __future__ import annotations

import json
import os

from .config import DATA_DIR, STATE_FILE
from .models import AppState, DrawSettings, Participant

_SETTINGS_FIELDS = set(DrawSettings.__dataclass_fields__)


def load_state() -> AppState:
    if not STATE_FILE.exists():
        return AppState()
    with open(STATE_FILE) as f:
        raw = json.load(f)
    participants = [
        Participant(
            id=p["id"],
            name=p["name"],
            email=p["email"],
            exclusions=p.get("exclusions", []),
        )
        for p in raw.get("participants", [])
    ]
    settings_raw = raw.get("settings", {})
    settings = DrawSettings(**{k: v for k, v in settings_raw.items() if k in _SETTINGS_FIELDS})
    return AppState(
        participants=participants,
        settings=settings,
        assignments=raw.get("assignments"),
        hide_assignments=raw.get("hide_assignments", False),
        send_status=raw.get("send_status", {}),
        send_errors=raw.get("send_errors", {}),
        gmail_account=raw.get("gmail_account"),
    )


def save_state(state: AppState) -> None:
    """Atomic write: dump to a temp file, then rename over the real one."""
    DATA_DIR.mkdir(exist_ok=True)
    raw = {
        "participants": [
            {"id": p.id, "name": p.name, "email": p.email, "exclusions": p.exclusions}
            for p in state.participants
        ],
        "settings": state.settings.__dict__,
        "assignments": state.assignments,
        "hide_assignments": state.hide_assignments,
        "send_status": state.send_status,
        "send_errors": state.send_errors,
        "gmail_account": state.gmail_account,
    }
    tmp = STATE_FILE.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(raw, f, indent=2)
    os.replace(tmp, STATE_FILE)
