"""Claim vs ground truth accounting.

A *claim* is something the web application says about itself: a line in the
status log box, a success page, a green pill. A claim may be asserted on,
because "does the status box work" is itself a feature under test. A claim may
never be the only thing a test passes on, because a claim can lie.

*Ground truth* is something observed outside the web application: the camera
picture, the Pi's own uptime, a file that really exists on the Pi, an ssh
server that really answers.

Tests record both through an EvidenceLog. A test that finishes without any
ground truth fails, unless it is explicitly marked claim_only with a reason.
"""

from __future__ import annotations

import dataclasses
import enum


class EvidenceKind(enum.Enum):
    CLAIM = "claim"
    GROUND_TRUTH = "ground truth"


@dataclasses.dataclass(frozen=True)
class Evidence:
    kind: EvidenceKind
    description: str
    detail: str
    passed: bool


class EvidenceLog:
    """Records every assertion a test makes, tagged by what kind it is."""

    def __init__(self) -> None:
        self.entries: list[Evidence] = []

    def claim(self, description: str, condition: object, detail: str = "") -> None:
        """Assert something the site says about itself."""
        self._record(EvidenceKind.CLAIM, description, condition, detail)

    def ground_truth(self, description: str, condition: object, detail: str = "") -> None:
        """Assert something observed outside the web application."""
        self._record(EvidenceKind.GROUND_TRUTH, description, condition, detail)

    def _record(self, kind: EvidenceKind, description: str, condition: object, detail: str) -> None:
        passed = bool(condition)
        self.entries.append(Evidence(kind, description, detail, passed))
        if passed:
            return
        # A failed claim is recorded and re-raised at the end of the test, not
        # here. Raising here stopped the test before it could gather the
        # ground truth: on welland, where the PoE status endpoint 500s, the
        # power-cycle test aborted on the status box and never watched the
        # board actually reboot -- reporting the first thing it happened to
        # check instead of what the user experiences. Ground truth still
        # raises: once an observation of reality has failed, carrying on
        # proves nothing.
        if kind is EvidenceKind.GROUND_TRUTH:
            raise AssertionError(self._message(kind, description, detail))

    @staticmethod
    def _message(kind: EvidenceKind, description: str, detail: str) -> str:
        message = f"[{kind.value}] {description}"
        return f"{message}\n  {detail}" if detail else message

    @property
    def failures(self) -> list[Evidence]:
        """Everything recorded that did not hold, in the order it was observed."""
        return [e for e in self.entries if not e.passed]

    @property
    def has_ground_truth(self) -> bool:
        return any(e.kind is EvidenceKind.GROUND_TRUTH and e.passed for e in self.entries)

    def summary(self) -> str:
        lines = []
        for e in self.entries:
            mark = "ok" if e.passed else "FAILED"
            line = f"  {mark:>6}  [{e.kind.value}] {e.description}"
            if e.detail:
                line = f"{line}\n            {e.detail}"
            lines.append(line)
        return "\n".join(lines) if lines else "  (no evidence recorded)"
