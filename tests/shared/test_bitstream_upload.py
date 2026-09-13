"""Can a person upload a bitstream through the form and see it running?

The claim is the success page. The ground truth is that the file really landed
on the Pi at the right size, that openFPGALoader really programmed the part,
and that the LEDs visibly changed and are now counting.

Known limitation: counter_test/top.bit is the same bitstream the "Blink LEDs"
button loads, so the camera proves "the LEDs changed and are counting" but not
"this upload is what is running". A distinctive design from
fpgas.online-test-designs closes that gap later.
"""

import re
import time
from pathlib import Path

import pytest

from e2e.camera import PICTURE_REGION, difference

BITSTREAM = Path(__file__).parents[2] / "fixtures" / "counter_test" / "top.bit"
# Absolute, because the shared tmux session is not necessarily at $HOME: the
# page's own "Blink LEDs" button leaves it in ~/Demos/counter_test, and a
# relative path then reports "No such file or directory" on a healthy board.
REMOTE = "~/Uploads/top.bit"

# PROVISIONAL. These cannot be calibrated until POST /pibup/upload stops
# returning 500, because no run has yet got as far as programming a board and
# watching it. They are deliberately low: the scene is dark and an LED change
# is a small bright patch in a large frame, so a mean difference stays modest.
# Revisit with real before/after frames once the upload endpoint is fixed.
CHANGED = 0.005
STILL_RUNNING = 0.002


def _picture_difference(a, b) -> float:
    """How much the picture changed, ignoring the clock overlay that always does."""
    return difference(a, b, region=PICTURE_REGION)


def _recently_written(text: str, window: int = 600) -> tuple[bool, str]:
    """Is the uploaded file's mtime within `window` seconds of the Pi's own clock?

    Both numbers come from the Pi, so this needs no agreement between the
    tester's clock and the board's.
    """
    stamps = re.findall(r"\b(\d{9,11})\b", text)
    if not stamps:
        return False, f"could not read an mtime from {text!r}"
    mtime = int(stamps[-1])
    now = re.search(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2})", text)
    age = time.time() - mtime
    return abs(age) <= window, f"file mtime {mtime} is {age:.0f}s old; the Pi said {now.group(1) if now else '?'}"


@pytest.mark.live
def test_uploaded_bitstream_programs_the_arty_and_changes_the_leds(board_page, evidence):
    session = board_page()
    page, terminal, camera = session.page, session.terminal, session.camera

    camera.check_live_with_recovery(timeout=60)
    before = camera.shot()

    page.set_input_files("#upform input[type=file]", str(BITSTREAM))
    page.click("#upform input[type=submit]")
    page.wait_for_load_state("domcontentloaded")

    # Read the rendered text, not the HTML source, and name the board. The
    # site runs with DEBUG=True, so a failed upload renders Django's technical
    # traceback -- whose source listing contains "handle_uploaded_file". The
    # old check, `"uploaded" in page.content()`, therefore passed on the very
    # crash this test exists to catch.
    landed = page.inner_text("body")
    evidence.claim(
        "the upload form reports success",
        "uploaded" in landed.lower() and f"pino={session.board.port}" in landed.replace(" ", ""),
        detail=f"landed on {page.url} showing: {landed[:400]!r}",
    )

    page.go_back()
    terminal.reset()
    terminal.wait_for_prompt()

    # The size alone does not prove THIS upload landed: the identical file from
    # a previous run, or another user's, satisfies it just as well. A person
    # checks the file is new, so ask for the timestamp too.
    listing = terminal.run(f"ls -l --time-style=+%Y-%m-%dT%H:%M {REMOTE}")
    shown, detail = listing.shows(str(BITSTREAM.stat().st_size))
    evidence.ground_truth("the bitstream really landed on the Pi at the right size", shown, detail=detail)

    stamped = terminal.run(f"date +%Y-%m-%dT%H:%M; stat -c %Y {REMOTE}")
    fresh, fresh_detail = _recently_written(stamped.text)
    evidence.ground_truth(
        "the file on the Pi was written just now, not left over from a previous run",
        fresh,
        detail=fresh_detail,
    )

    programming = terminal.run(f"openFPGALoader -b arty {REMOTE}", timeout=180)
    status = terminal.exit_status()
    evidence.ground_truth(
        "openFPGALoader programmed the FPGA",
        status == 0,
        detail=f"exit status {status}; output: {programming.text[-400:]!r}",
    )

    camera.check_live_with_recovery(timeout=60)
    after = camera.shot()
    changed = _picture_difference(before, after)
    evidence.ground_truth(
        "the board looks different from before the upload",
        changed > CHANGED,
        detail=f"picture difference {changed:.4f} (threshold {CHANGED})",
    )

    later = camera.shot()
    counting = _picture_difference(after, later)
    evidence.ground_truth(
        "the design is visibly running, not frozen",
        counting > STILL_RUNNING,
        detail=f"picture difference across two shots {counting:.4f} (threshold {STILL_RUNNING})",
    )
