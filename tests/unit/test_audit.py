import datetime as dt

from e2e.audit import (
    COLUMNS,
    BoardAudit,
    Check,
    audit_board,
    camera_note,
    poe_note,
    render_markdown,
    render_text,
    run_journey,
    unopened_board_audit,
)
from e2e.board import Board
from e2e.session import open_board

WHEN = dt.datetime(2026, 9, 14, 3, 0, 0, tzinfo=dt.timezone.utc)
PI7 = Board("pi7", 7, "")
PI2 = Board("pi2", 2, "")


def _sees_the_board(log):
    log.ground_truth("the camera is showing a live picture", True, detail="clock '03:00:01' -> '03:00:04'")


def _board_is_dead(log):
    log.ground_truth("the camera is showing a live picture", False, detail="no clock readable")
    log.ground_truth("never reached", True)


def _claim_fails_but_reality_holds(log):
    log.claim("the status box says set power", False, detail="the box added nothing")
    log.ground_truth("the Pi rebooted", True, detail="uptime 12.0s")


def test_a_journey_whose_every_observation_held_passes():
    check = run_journey("camera", _sees_the_board)
    assert check.passed
    assert check.detail == "clock '03:00:01' -> '03:00:04'"


def test_a_failed_ground_truth_fails_the_cell_and_quotes_what_was_seen():
    check = run_journey("camera", _board_is_dead)
    assert not check.passed
    assert check.detail == "the camera is showing a live picture: no clock readable"


def test_a_failed_claim_fails_the_cell_even_when_reality_held():
    check = run_journey("power cycle", _claim_fails_but_reality_holds)
    assert not check.passed
    assert "the box added nothing" in check.detail


def test_a_crash_inside_the_journey_is_a_failure_that_names_the_crash():
    def _explodes(log):
        raise RuntimeError("Target page, context or browser has been closed\nmore lines")

    check = run_journey("terminal", _explodes)
    assert not check.passed
    assert check.detail == "RuntimeError: Target page, context or browser has been closed"


def test_a_journey_that_observed_nothing_does_not_pass():
    check = run_journey("ssh", lambda log: None)
    assert not check.passed
    assert "observed nothing" in check.detail


def test_a_journey_that_only_recorded_claims_does_not_pass_unless_told_claims_are_enough():
    only_claims = lambda log: log.claim("the heading names pi7", True)  # noqa: E731
    check = run_journey("page", only_claims)
    assert not check.passed
    assert check.detail == "only the site's own claims were observed"
    assert run_journey("page", only_claims, needs_ground_truth=False).passed


def test_the_camera_note_says_when_the_reset_button_was_needed():
    def _needed_reset(log):
        log.ground_truth("live", True, detail="the picture needed the page's 'reset video player' button: x -> y")

    assert run_journey("camera", _needed_reset, note_from=camera_note).cell == "ok (reset needed)"

    def _needed_play(log):
        log.ground_truth("live", True, detail="the picture needed the player's Play button: x -> y")

    assert run_journey("camera", _needed_play, note_from=camera_note).cell == "ok (play needed)"
    assert run_journey("camera", _sees_the_board, note_from=camera_note).cell == "ok"


def test_the_poe_note_is_the_word_the_box_used():
    def _says_on(log):
        log.claim("the status box reports the PoE state", True, detail="power on")
        return "on"

    check = run_journey("poe status", _says_on, note_from=poe_note, needs_ground_truth=False)
    assert check.passed
    assert check.cell == "ok (on)"


def test_the_poe_cell_fails_when_the_box_never_said():
    def _silent(log):
        log.claim("the status box reports the PoE state", False, detail="'power' never appeared")
        return ""

    assert run_journey("poe status", _silent, note_from=poe_note).cell == "FAIL (not shown)"


def _rows():
    healthy = BoardAudit(PI7, [Check(c, True, f"{c} fine") for c in COLUMNS])
    broken = BoardAudit(
        PI2,
        [
            Check("page", True, "heading reads 'Accessing pi2'"),
            Check("camera", False, "no clock readable; player {'readyState': 0}"),
            Check("terminal", False, "no shell prompt within 45s"),
            Check("poe status", True, "power on", note="on"),
            Check("ssh", False, "Connection refused"),
            Check("upload", False, "the upload form reports success: showing 'Server Error (500)'"),
            Check("power cycle", False, "the camera feed is live before the reset: never sampled"),
        ],
    )
    return [healthy, broken]


def test_the_text_table_has_one_row_per_board_and_the_reasons_below():
    text = render_text("ps1", _rows(), when=WHEN)
    lines = text.splitlines()
    assert lines[0] == "### ps1: 2 boards, audited 2026-09-14T03:00:00Z"
    header = ["board", "page", "camera", "terminal", "poe", "status", "ssh", "upload", "power", "cycle"]
    assert lines[1].split() == header
    assert lines[2].startswith("pi7") and lines[2].count("ok") == 7
    assert lines[3].startswith("pi2") and "FAIL" in lines[3] and "ok (on)" in lines[3]
    assert "  pi2 camera (0s): no clock readable; player {'readyState': 0}" in lines
    assert "  pi2 ssh (0s): Connection refused" in lines
    why = lines[lines.index("why:") : lines.index("seen:")]
    assert not any(line.startswith("  pi7") for line in why)


def test_the_markdown_table_carries_the_same_cells():
    md = render_markdown("ps1", _rows(), when=WHEN)
    assert "| board | page | camera | terminal | poe status | ssh | upload | power cycle |" in md
    assert "| pi7 | ok | ok | ok | ok | ok | ok | ok |" in md
    assert "| pi2 | ok | FAIL | FAIL | ok (on) | FAIL | FAIL | FAIL |" in md
    assert "- **pi2 terminal** (0s): no shell prompt within 45s" in md


def test_a_row_lists_its_failures_in_order():
    assert [c.name for c in _rows()[1].failures] == ["camera", "terminal", "ssh", "upload", "power cycle"]


def test_a_cell_records_how_long_the_answer_took():
    import time

    def _slow(log):
        time.sleep(0.05)
        log.ground_truth("fine", True)

    check = run_journey("camera", _slow)
    assert check.seconds >= 0.05
    assert check.timed.startswith("ok ")
    assert check.timed.endswith("s")


def test_the_report_says_what_proved_each_pass():
    text = render_text("ps1", _rows(), when=WHEN)
    assert "seen:" in text
    assert "  pi7 camera (0s): camera fine" in text
    md = render_markdown("ps1", _rows(), when=WHEN)
    assert "- pi7 upload (0s): upload fine" in md


def test_a_skipped_cell_is_neither_a_pass_nor_a_failure():
    row = BoardAudit(PI7, [Check("camera", True, "fine"), Check("upload", False, "not tried", skipped=True)])
    assert row.failures == []
    assert row.check("upload").cell == "skipped"
    assert "upload" not in render_text("ps1", [row], when=WHEN).split("seen:")[-1]



def test_rendering_zero_rows_does_not_raise():
    assert "0 boards" in render_text("ps1", [], when=WHEN)
    assert "0 boards" in render_markdown("ps1", [], when=WHEN)


class _Page:
    def __init__(self, fail_goto):
        self.fail_goto = fail_goto

    def on(self, *a, **k):
        pass

    def goto(self, *a, **k):
        if self.fail_goto:
            raise TimeoutError("Page.goto: Timeout 30000ms exceeded.\nCall log: ...")

    def __getattr__(self, name):
        return lambda *a, **k: None


class _Context:
    closed = False

    def __init__(self, fail_goto):
        self.page = _Page(fail_goto)

    def new_page(self):
        return self.page

    def close(self):
        self.closed = True


class _Browser:
    def __init__(self, fail_goto):
        self.context = _Context(fail_goto)

    def new_context(self, **_):
        return self.context


def test_a_page_that_will_not_open_closes_its_context_and_raises():
    import pytest

    from e2e.site import Site

    browser = _Browser(fail_goto=True)
    with pytest.raises(TimeoutError):
        open_board(browser, {}, Site.from_name("ps1"), PI7)
    assert browser.context.closed


def test_a_board_that_would_not_open_becomes_a_failed_row_quoting_the_exception():
    row = unopened_board_audit(PI7, TimeoutError("Page.goto: Timeout 30000ms exceeded.\nCall log: ..."))
    assert row.board is PI7
    assert [c.name for c in row.checks] == ["page"]
    page = row.check("page")
    assert not page.passed and not page.skipped
    assert "TimeoutError: Page.goto: Timeout 30000ms exceeded." in page.detail
    assert row.failures == [page]
    # and it renders, with the reason under the table
    assert "TimeoutError" in render_text("ps1", [row], when=WHEN)


def _acorn_row():
    reason = "acorn-host: no bitstream fixture or loader command for FPGA type 'acorn'"
    checks = [Check(c, True, f"{c} fine") for c in COLUMNS if c != "upload"]
    checks.append(Check("upload", False, reason, skipped=True))
    return BoardAudit(Board("acorn-host", 1, "Acorn CLE-215+"), checks), reason


def test_a_skipped_cell_has_its_reason_in_both_renderers():
    row, reason = _acorn_row()
    text = render_text("welland", [row], when=WHEN)
    assert "skipped:" in text.splitlines()
    assert f"  acorn-host upload: {reason}" in text.splitlines()
    md = render_markdown("welland", [row], when=WHEN)
    assert "Skipped:" in md
    assert f"- **acorn-host upload**: {reason}" in md


def test_no_skipped_section_when_nothing_was_skipped():
    assert "skipped:" not in render_text("ps1", _rows(), when=WHEN)
    assert "Skipped:" not in render_markdown("ps1", _rows(), when=WHEN)


def _stub_journeys(monkeypatch, called):
    """Every journey records that it ran and observes one passing ground truth."""
    from e2e import journeys

    def stub(name, result=None):
        def run(*args, **kwargs):
            called.append(name)
            log = next(a for a in args if hasattr(a, "ground_truth"))
            log.ground_truth(f"{name} observed", True, detail=f"{name} fine")
            return result

        return run

    for name, result in (
        ("page_names_the_board", None),
        ("camera_is_live", None),
        ("terminal_reaches_the_board", None),
        ("poe_status_is_reported", "on"),
        ("direct_ssh_works", None),
        ("upload_programs_the_board", None),
        ("reset_power_cycles_the_board", None),
    ):
        monkeypatch.setattr(journeys, name, stub(name, result))


class _FakeSession:
    def __init__(self, board):
        self.board = board


def test_the_audit_marks_an_acorns_upload_skipped_with_the_reason_and_never_runs_it(monkeypatch):
    called = []
    _stub_journeys(monkeypatch, called)
    row = audit_board(_FakeSession(Board("acorn-host", 1, "Acorn CLE-215+")), known_hosts=None, disruptive=True)
    upload = row.check("upload")
    assert upload.skipped and not upload.passed
    assert "acorn" in upload.detail
    assert "upload_programs_the_board" not in called
    assert "reset_power_cycles_the_board" in called  # the other disruptive journey still runs
    assert row.failures == []


def test_without_disruptive_the_upload_and_power_cycle_are_skipped_and_never_run(monkeypatch):
    called = []
    _stub_journeys(monkeypatch, called)
    row = audit_board(_FakeSession(Board("pi-sw1-p2", 2, "Digilent Arty A7-35T")), known_hosts=None)
    for name in ("upload", "power cycle"):
        cell = row.check(name)
        assert cell.skipped and cell.detail == "needs --disruptive"
    assert "upload_programs_the_board" not in called
    assert "reset_power_cycles_the_board" not in called
    assert {"camera_is_live", "terminal_reaches_the_board", "direct_ssh_works"} <= set(called)
    assert row.failures == []
    assert "needs --disruptive" in render_text("welland", [row], when=WHEN)


def test_with_disruptive_an_arty_runs_both_disruptive_journeys_last(monkeypatch):
    called = []
    _stub_journeys(monkeypatch, called)
    row = audit_board(_FakeSession(Board("pi-sw1-p2", 2, "Digilent Arty A7-35T")), known_hosts=None, disruptive=True)
    assert called[-2:] == ["upload_programs_the_board", "reset_power_cycles_the_board"]
    assert not any(c.skipped for c in row.checks)


def test_a_busy_terminal_is_a_skipped_cell_with_the_reason_not_a_failure():
    from e2e.terminal import TerminalBusy

    def visitor_typing(_log):
        raise TerminalBusy("a visitor is using the terminal: 'ls' is on the shell's line, so nothing was typed")

    cell = run_journey("terminal", visitor_typing)
    assert cell.skipped and not cell.passed
    assert cell.cell == "skipped"
    assert "a visitor is using the terminal" in cell.detail
    row = BoardAudit(PI7, [cell])
    assert row.failures == []
    assert "a visitor is using the terminal" in render_text("ps1", [row], when=WHEN)


def test_a_dead_terminal_is_still_a_failed_cell():
    from e2e.terminal import TerminalLost

    def dead(_log):
        raise TerminalLost("no shell prompt line is visible")

    cell = run_journey("terminal", dead)
    assert not cell.skipped and not cell.passed
    assert "TerminalLost" in cell.detail


def test_a_busy_terminal_does_not_hide_a_failure_the_journey_already_recorded():
    from e2e.terminal import TerminalBusy

    def failed_then_busy(log):
        log.claim("the status box said so", False, detail="it did not")
        raise TerminalBusy("a visitor is using the terminal: 'ls'")

    cell = run_journey("terminal", failed_then_busy)
    assert not cell.skipped and not cell.passed
    assert "the status box said so" in cell.detail
