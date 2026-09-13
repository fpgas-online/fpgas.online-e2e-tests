"""Does 'turn it off and on again' actually turn the board off and on again?

The claim is the status box. The ground truth is that the camera stops seeing
a live picture -- the camera runs on the Pi, so the feed dying IS the Pi
dying -- and that the Pi's own uptime went backwards afterwards.
"""

import re
import time

import pytest

# /proc/uptime is exactly two floats on one line: seconds up, seconds idle.
# Anchored, because an unanchored number picks up the clock in the prompt
# ("06:25:33 pi@pi2:~ $" yields 33) and a plausible-looking wrong answer is
# worse than no answer.
UPTIME = re.compile(r"^\s*(\d+\.\d+)\s+\d+\.\d+\s*$", re.MULTILINE)

# What the board page says about itself while it reboots: the kernel "can take
# up to 2 minutes", and the video feed runs about 60s behind. The waits below
# come from those numbers rather than from guesses.
BOOT_BUDGET = 300.0


def _uptime_seconds(terminal, evidence, when: str) -> float:
    out = terminal.run("cat /proc/uptime")
    match = UPTIME.search(out.text)
    evidence.ground_truth(
        f"the Pi reported its uptime {when}",
        match is not None,
        detail=f"terminal showed {out.text!r}",
    )
    seconds = float(match.group(1))
    # Cross-check the number itself on the screen, not a full stop that any
    # prompt would satisfy.
    shown, detail = out.shows(match.group(1))
    evidence.ground_truth(f"the uptime is legible on screen {when}", shown, detail=detail)
    return seconds


@pytest.mark.live
def test_reset_button_power_cycles_the_board(board_page, evidence):
    session = board_page()
    board, page, camera = session.board, session.page, session.camera
    name = board.hostname

    live, detail = camera.check_live(timeout=60)
    evidence.ground_truth(f"{name}'s camera feed is live before the reset", live, detail=detail)

    before = _uptime_seconds(session.terminal, evidence, "before the reset")

    # Everything the box says from here on is a consequence of the click. The
    # box accumulates and the click itself makes the page re-ask for the PoE
    # state, so without this baseline the status assertion matches text the
    # click produced whether or not the port was ever switched.
    baseline = session.status.text()
    clicked_at = time.monotonic()
    page.click(f"#reset{board.port}")

    seen, detail = session.status.wait_for_new("set power", baseline, timeout=30)
    evidence.claim("the status box reports the PoE port being switched", seen, detail=detail)

    stopped, detail = camera.check_not_live(timeout=90)
    evidence.ground_truth(f"{name} stopped sending video, so it really lost power", stopped, detail=detail)

    returned, detail = camera.check_live(timeout=BOOT_BUDGET)
    evidence.ground_truth(f"{name}'s camera feed came back", returned, detail=detail)

    session.terminal.reconnect()
    after = _uptime_seconds(session.terminal, evidence, "after the reset")

    evidence.ground_truth(
        "the Pi's uptime went backwards, so it really rebooted",
        after < before,
        detail=f"before={before:.1f}s after={after:.1f}s",
    )
    # The reasoning a person does: it cannot have been up for longer than the
    # time since I pressed the button. A fixed ceiling instead fails a slow
    # but perfectly good power cycle, because the waits above can legitimately
    # take several minutes.
    elapsed = time.monotonic() - clicked_at
    evidence.ground_truth(
        "the Pi booted since the button was pressed",
        after <= elapsed + 30,
        detail=f"uptime {after:.1f}s, {elapsed:.1f}s since the click",
    )

    seen, detail = session.status.wait_for_new("ssh server started.", baseline, timeout=120)
    evidence.claim("the status box reports the Pi's ssh server coming back", seen, detail=detail)
