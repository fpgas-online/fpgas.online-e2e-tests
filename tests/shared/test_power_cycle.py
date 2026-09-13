"""Does 'turn it off and on again' actually turn the board off and on again?

The claim is the status box. The ground truth is that the camera stops seeing
a live picture -- the camera runs on the Pi, so the feed dying IS the Pi
dying -- and that the Pi's own uptime went backwards afterwards.
"""

import re

import pytest

UPTIME = re.compile(r"([\d.]+)\s")


def _uptime_seconds(terminal, evidence, when: str) -> float:
    out = terminal.run("cat /proc/uptime")
    shown, detail = out.shows(".")
    evidence.ground_truth(f"the Pi reported its uptime {when}", shown, detail=detail)
    match = UPTIME.search(out.text)
    assert match, f"could not read an uptime from {out.text!r}"
    return float(match.group(1))


@pytest.mark.live
def test_reset_button_power_cycles_the_board(board_page, evidence):
    session = board_page()
    board, page = session.board, session.page
    name = board.hostname

    detail = session.camera.wait_until_live(timeout=60)
    evidence.ground_truth(f"{name}'s camera feed is live before the reset", True, detail=detail)

    before = _uptime_seconds(session.terminal, evidence, "before the reset")

    page.click(f"#reset{board.port}")

    seen, detail = session.status.wait_for("power", timeout=30)
    evidence.claim("the status box reports the PoE port being switched", seen, detail=detail)

    detail = session.camera.wait_until_not_live(timeout=60)
    evidence.ground_truth(f"{name} stopped sending video, so it really lost power", True, detail=detail)

    detail = session.camera.wait_until_live(timeout=240)
    evidence.ground_truth(f"{name}'s camera feed came back", True, detail=detail)

    session.terminal.reconnect()
    after = _uptime_seconds(session.terminal, evidence, "after the reset")

    evidence.ground_truth(
        "the Pi's uptime went backwards, so it really rebooted",
        after < before,
        detail=f"before={before:.1f}s after={after:.1f}s",
    )
    evidence.ground_truth(
        "the Pi has only just booted",
        after < 240,
        detail=f"uptime after the reset was {after:.1f}s",
    )

    seen, detail = session.status.wait_for("ssh", timeout=120)
    evidence.claim("the status box reports the Pi's ssh server coming back", seen, detail=detail)
