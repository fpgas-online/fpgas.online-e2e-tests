"""Choosing which board to test on.

One board per run, picked at random, so a user is unlikely to collide with a
test and the fleet is exercised evenly. The seed is printed by the test
session so any run can be replayed against the same board.

Every board is treated as an Arty. The sites do not reliably say what FPGA is
fitted -- ps1 names none at all -- so filtering by the advertised type only
meant refusing to test anything. A board that turns out not to be an Arty
fails inside the test, where the failure names the real problem.
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
