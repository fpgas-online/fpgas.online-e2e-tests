"""Choosing which board to test on.

One board per run, picked at random, so a user is unlikely to collide with a
test and the fleet is exercised evenly. The seed is printed by the test
session so any run can be replayed against the same board.
"""

from __future__ import annotations

import enum
import random

from e2e.board import Board


class OnDead(enum.Enum):
    """What to do when the chosen board turns out not to be working."""

    FAIL = "fail"
    RETRY = "retry"


class NoSuchBoard(RuntimeError):
    pass


def choose(boards: list[Board], kind: str, seed: int) -> list[Board]:
    """Candidate boards of `kind`, in a seeded random order."""
    candidates = [b for b in boards if b.kind == kind]
    if not candidates:
        listed = ", ".join(sorted({b.kind for b in boards})) or "none"
        raise NoSuchBoard(f"the site lists no {kind!r} board; it lists: {listed}")
    random.Random(seed).shuffle(candidates)
    return candidates
