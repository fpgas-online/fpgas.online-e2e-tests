"""What a test does when a visitor is using the shared terminal: skip, unless that would hide a failure."""

from __future__ import annotations

from typing import NoReturn

import pytest

from e2e.evidence import EvidenceLog
from e2e.terminal import TerminalBusy


def skip_for_busy_terminal(evidence: EvidenceLog, exc: TerminalBusy) -> NoReturn:
    """Skip with the reason (`-ra` lists it), but fail if evidence already recorded did not hold.

    A visitor on the terminal is not a fault in the board, so it is not a
    failure. But a skipped test is exempt from the evidence check, so a claim
    already recorded as False (with --on-dead retry, a dead board that was
    passed over) would be lost; that must still fail the run.
    """
    if evidence.failures:
        pytest.fail(
            f"{exc}; and the evidence already recorded did not hold:\n"
            + "\n".join(f"  [{e.kind.value}] {e.description}\n    {e.detail}" for e in evidence.failures),
            pytrace=False,
        )
    pytest.skip(str(exc))
