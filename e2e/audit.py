"""Auditing every board at a site: the same journeys, one row per board.

Where a test picks one board and fails on the first thing wrong, the audit
visits every board the index lists and records the outcome of each journey
in a table -- what a person walking the rack with a checklist would produce.
It measures nothing the tests do not: each cell is a journey from
e2e.journeys run against a fresh EvidenceLog, and a cell passes only if
every observation in it held.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import time
from collections.abc import Callable

from e2e.board import Board
from e2e.evidence import EvidenceLog

COLUMNS = ("page", "camera", "terminal", "poe status", "ssh", "upload", "power cycle")


@dataclasses.dataclass(frozen=True)
class Check:
    """One cell of the table."""

    name: str
    passed: bool
    detail: str
    note: str = ""  # a word for the cell itself: "reset needed", "on", "off"
    seconds: float = 0.0  # how long a person waited for this answer
    skipped: bool = False  # not tried this run; neither a pass nor a failure

    @property
    def cell(self) -> str:
        if self.skipped:
            return "skipped"
        word = "ok" if self.passed else "FAIL"
        return f"{word} ({self.note})" if self.note else word

    @property
    def timed(self) -> str:
        return f"{self.cell} {self.seconds:.0f}s"


@dataclasses.dataclass
class BoardAudit:
    """One row: a board and the outcome of each check."""

    board: Board
    checks: list[Check] = dataclasses.field(default_factory=list)

    def check(self, name: str) -> Check | None:
        return next((c for c in self.checks if c.name == name), None)

    @property
    def failures(self) -> list[Check]:
        return [c for c in self.checks if not c.passed and not c.skipped]


def run_journey(
    name: str,
    journey: Callable[[EvidenceLog], object],
    note_from=None,
    needs_ground_truth: bool = True,
) -> Check:
    """Run one journey against a fresh log and reduce it to a cell.

    A ground-truth failure raises out of the journey; a failed claim is left
    in the log. Either fails the cell. Anything else that escapes -- a page
    that would not load, a terminal that vanished -- fails the cell too,
    quoting the exception, because "the tool crashed" is not "the board
    works". The detail is every failed observation, in order, so the reason
    a person reads under the table is what was actually seen.

    A cell passes on claims alone only where nothing else is possible and
    the caller says so: what the page's heading reads, what the status box
    says. Everywhere else it needs ground truth, as a test does.
    """
    log = EvidenceLog()
    crashed = ""
    result = None
    started = time.monotonic()
    try:
        result = journey(log)
    except AssertionError as exc:
        # A failed ground truth is already in the log. Any other assertion is
        # not, and must not vanish.
        if not log.failures:
            crashed = f"AssertionError: {str(exc).splitlines()[0][:300]}"
    except Exception as exc:  # noqa: BLE001 - the cell must say what happened
        crashed = f"{type(exc).__name__}: {str(exc).splitlines()[0][:300]}"
    failed = [f"{e.description}: {e.detail}" if e.detail else e.description for e in log.failures]
    if crashed:
        failed.append(crashed)
    if failed:
        passed, detail = False, "; ".join(failed)
    elif not log.entries:
        passed, detail = False, "the journey observed nothing"
    elif needs_ground_truth and not log.has_ground_truth:
        passed, detail = False, "only the site's own claims were observed"
    else:
        passed, detail = True, "; ".join(e.detail for e in log.entries if e.detail)
    note = note_from(result, log) if note_from else ""
    return Check(name=name, passed=passed, detail=detail, note=note, seconds=time.monotonic() - started)


DISRUPTIVE = ("upload", "power cycle")


def audit_board(session, known_hosts, quick: bool = False) -> BoardAudit:
    """Every journey, in the order a person would try them, on one open board.

    The disruptive ones come last -- the upload reprograms the FPGA and Reset
    reboots the Pi -- so that the readings before them describe the board as
    a user finds it. `quick` leaves those two out, marked skipped, for a
    look at the fleet that touches nothing.
    """
    from e2e import journeys  # noqa: PLC0415 - journeys imports the session types this module renders

    row = BoardAudit(session.board)
    steps = [
        ("page", lambda log: journeys.page_names_the_board(session, log), None, False),
        ("camera", lambda log: journeys.camera_is_live(session, log), camera_note, True),
        ("terminal", lambda log: journeys.terminal_reaches_the_board(session, log), None, True),
        ("poe status", lambda log: journeys.poe_status_is_reported(session, log), poe_note, False),
        ("ssh", lambda log: journeys.direct_ssh_works(session, log, known_hosts), None, True),
        ("upload", lambda log: journeys.upload_programs_the_board(session, log), None, True),
        ("power cycle", lambda log: journeys.reset_power_cycles_the_board(session, log), None, True),
    ]
    for name, journey, note_from, needs_ground_truth in steps:
        if quick and name in DISRUPTIVE:
            row.checks.append(Check(name=name, passed=False, detail="not tried (--quick)", skipped=True))
            continue
        row.checks.append(run_journey(name, journey, note_from=note_from, needs_ground_truth=needs_ground_truth))
    return row


def camera_note(_result, log: EvidenceLog) -> str:
    """Say when the picture only came after a press: Play, or the page's reset button."""
    for entry in log.entries:
        if not entry.passed:
            continue
        if "reset video player" in entry.detail:
            return "reset needed"
        if "Play button" in entry.detail:
            return "play needed"
    return ""


def poe_note(result, _log: EvidenceLog) -> str:
    return result or "not shown"


def _stamp(when: dt.datetime | None) -> str:
    when = when or dt.datetime.now(dt.timezone.utc)
    return when.strftime("%Y-%m-%dT%H:%M:%SZ")


def render_text(site: str, rows: list[BoardAudit], when: dt.datetime | None = None) -> str:
    """A fixed-width table for the terminal, with the failures spelled out below it."""
    widths = {c: max(len(c), *(len(r.check(c).cell) if r.check(c) else 1 for r in rows)) for c in COLUMNS}
    name_width = max(len("board"), *(len(r.board.hostname) for r in rows))
    lines = [f"### {site}: {len(rows)} boards, audited {_stamp(when)}"]
    lines.append("  ".join(["board".ljust(name_width), *(c.ljust(widths[c]) for c in COLUMNS)]))
    for row in rows:
        cells = [(row.check(c).cell if row.check(c) else "-").ljust(widths[c]) for c in COLUMNS]
        lines.append("  ".join([row.board.hostname.ljust(name_width), *cells]))
    failures = [(row.board.hostname, c) for row in rows for c in row.failures]
    if failures:
        lines.append("")
        lines.append("why:")
        for hostname, check in failures:
            lines.append(f"  {hostname} {check.name} ({check.seconds:.0f}s): {check.detail}")
    passes = [(row.board.hostname, c) for row in rows for c in row.checks if c.passed and c.detail and not c.skipped]
    if passes:
        # What proved each pass, because a table of "ok" is a claim until it
        # says what was seen.
        lines.append("")
        lines.append("seen:")
        for hostname, check in passes:
            lines.append(f"  {hostname} {check.name} ({check.seconds:.0f}s): {check.detail}")
    return "\n".join(lines)


def render_markdown(site: str, rows: list[BoardAudit], when: dt.datetime | None = None) -> str:
    """The same table for a GitHub step summary or a report file."""
    lines = [f"### {site}: {len(rows)} boards, audited {_stamp(when)}", ""]
    lines.append("| board | " + " | ".join(COLUMNS) + " |")
    lines.append("|---|" + "|".join("---" for _ in COLUMNS) + "|")
    for row in rows:
        cells = [row.check(c).cell if row.check(c) else "-" for c in COLUMNS]
        lines.append(f"| {row.board.hostname} | " + " | ".join(cells) + " |")
    failures = [(row.board.hostname, c) for row in rows for c in row.failures]
    if failures:
        lines.append("")
        lines.append("Why:")
        lines.append("")
        for hostname, check in failures:
            lines.append(f"- **{hostname} {check.name}** ({check.seconds:.0f}s): {check.detail}")
    passes = [(row.board.hostname, c) for row in rows for c in row.checks if c.passed and c.detail and not c.skipped]
    if passes:
        lines.append("")
        lines.append("Seen:")
        lines.append("")
        for hostname, check in passes:
            lines.append(f"- {hostname} {check.name} ({check.seconds:.0f}s): {check.detail}")
    return "\n".join(lines) + "\n"
