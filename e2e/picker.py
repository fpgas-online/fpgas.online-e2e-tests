"""Choosing which board to test on.

One board per run, picked at random, so a user is unlikely to collide with a
test and the fleet is exercised evenly. The seed is printed by the test
session so any run can be replayed against the same board.

Every board the index lists is a candidate: filtering by advertised type meant
refusing to test anything, since ps1 names none. What FPGA a board has is
Board.fpga_type, read from what the site shows; a test that needs a particular
type for its fixtures skips, naming the type, rather than assuming one.
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


def choose(boards: list[Board], seed: int) -> list[Board]:
    """Every board the site lists, in a seeded random order."""
    if not boards:
        raise NoSuchBoard("the site lists no boards at all")
    candidates = list(boards)
    random.Random(seed).shuffle(candidates)
    return candidates
