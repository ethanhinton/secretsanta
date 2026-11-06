"""Random derangement with per-person exclusions, via backtracking.

Every participant is assigned exactly one distinct recipient ("who they draw").
Constraints honoured:
  * nobody draws themselves,
  * nobody draws a person they have excluded,
  * (optional) no reciprocal pairs: A draws B and B draws A is avoided.

Backtracking guarantees a valid assignment is found whenever one exists, so
unlike naive shuffle-and-retry this does not degrade as exclusions pile up.
"""
from __future__ import annotations

import random
from typing import Dict, List, Optional

from .models import Participant


def draw_names(
    participants: List[Participant],
    no_reciprocal: bool = False,
    rng: Optional[random.Random] = None,
) -> Dict[str, str]:
    """Return {giver_id: recipient_id} or raise ValueError if impossible."""
    rng = rng or random.SystemRandom()
    n = len(participants)
    if n < 2:
        raise ValueError("Need at least two participants to draw.")

    allowed: Dict[str, List[str]] = {}
    for p in participants:
        excluded = set(p.exclusions)
        candidates = [q.id for q in participants if q.id != p.id and q.id not in excluded]
        if not candidates:
            raise ValueError(
                f"{p.name} can't draw anyone — their exclusions cover the whole list."
            )
        allowed[p.id] = candidates

    # Most-constrained first: prunes the search tree early.
    order = sorted(allowed, key=lambda pid: len(allowed[pid]))
    assignment: Dict[str, str] = {}
    taken: set = set()

    def solve(i: int) -> bool:
        if i == n:
            return True
        giver = order[i]
        candidates = [r for r in allowed[giver] if r not in taken]
        rng.shuffle(candidates)
        for rec in candidates:
            # If the recipient already chose this giver, that would be a
            # reciprocal pair. (If the recipient is assigned later, the check
            # fires symmetrically when they are assigned.)
            if no_reciprocal and assignment.get(rec) == giver:
                continue
            assignment[giver] = rec
            taken.add(rec)
            if solve(i + 1):
                return True
            del assignment[giver]
            taken.discard(rec)
        return False

    if not solve(0):
        raise ValueError(
            "No valid assignment exists for these exclusions. "
            "Remove some exclusions and try again."
        )
    return assignment
