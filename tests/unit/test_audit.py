import datetime as dt

from e2e.audit import COLUMNS, BoardAudit, Check, camera_note, poe_note, render_markdown, render_text, run_journey
from e2e.board import Board

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
    assert not any(line.startswith("  pi7") for line in lines)


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
