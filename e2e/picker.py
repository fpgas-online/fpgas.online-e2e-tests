"""Choosing which board to test on.

One board per run, picked at random, so a user is unlikely to collide with a
test and the fleet is exercised evenly. The seed is printed by the test
session so any run can be replayed against the same board.

Boards with a camera come first in the seeded order (see Board.has_camera);
a board known to have none is tried only when no board with one is usable, or
when --boards names it.

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


def choose(boards: list[Board], seed: int, wanted: set[str] | frozenset[str] = frozenset()) -> list[Board]:
    """Every board the site lists, in a seeded random order.

    With `wanted` (--boards) only the listed boards named there are candidates;
    if none of the named boards is listed, that is an error naming them, and
    never a quiet choice of some other board.
    """
    if not boards:
        raise NoSuchBoard("the site lists no boards at all")
    candidates = list(boards)
    if wanted:
        candidates = [b for b in candidates if b.hostname in wanted]
        if not candidates:
            raise NoSuchBoard(
                f"--boards names {sorted(wanted)}, and the site lists none of them "
                f"(it lists {sorted(b.hostname for b in boards)})"
            )
    random.Random(seed).shuffle(candidates)
    # Stable, so the seeded order holds inside each group: boards with a
    # camera, then boards not yet looked at, then boards known to have none.
    candidates.sort(key=_camera_rank)
    return candidates


def _camera_rank(board: Board) -> int:
    return {True: 0, None: 1, False: 2}[board.has_camera]


def why_picked(board: Board, boards: list[Board], seed: int, wanted: set[str] | frozenset[str] = frozenset()) -> str:
    """One line saying why `board` was tried, for the test output and the job summary."""
    with_camera = sum(1 for b in boards if b.has_camera)
    if board.has_camera:
        reason = "has a camera"
    elif board.has_camera is False:
        reason = "has no camera" if board.hostname in wanted else "has no camera, tried after the boards that have one"
    else:
        reason = "the site does not say whether it has a camera"
    if board.hostname in wanted:
        reason = f"named by --boards; {reason}"
    return f"picked {board.hostname}: {reason}; seed {seed}; {with_camera} of {len(boards)} boards have a camera"
