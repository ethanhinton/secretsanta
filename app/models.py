"""Data models for participants, draw settings, and overall app state."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional


def new_id() -> str:
    """Short unique id for a participant."""
    return uuid.uuid4().hex[:12]


@dataclass
class Participant:
    id: str
    name: str
    email: str
    # Ids of participants this person must NOT be drawn for (i.e. they must
    # not give a gift to).
    exclusions: List[str] = field(default_factory=list)


@dataclass
class DrawSettings:
    # Everything below is used when composing the email.
    subject: str = "Secret Santa draw! (DO NOT REPLY)"
    max_spend: str = ""  # e.g. "15" — empty means no spend line in the email
    currency: str = "£"
    notes: str = ""  # extra free-text block, e.g. "No vouchers!"
    # If True, the draw avoids reciprocal pairs (A draws B and B draws A).
    no_reciprocal: bool = False


@dataclass
class AppState:
    participants: List[Participant] = field(default_factory=list)
    settings: DrawSettings = field(default_factory=DrawSettings)
    # giver_id -> recipient_id. None until a draw has been made.
    assignments: Optional[Dict[str, str]] = None
    # participant_id -> "pending" | "sending" | "sent" | "failed"
    send_status: Dict[str, str] = field(default_factory=dict)
    # participant_id -> last error message (only present for "failed")
    send_errors: Dict[str, str] = field(default_factory=dict)
    # The Gmail account that was connected via OAuth, for display purposes.
    gmail_account: Optional[str] = None
