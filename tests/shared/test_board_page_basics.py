"""The two things a board page has to give you before anything else matters:
a terminal you can type in, and a camera you can watch.

Every other test in the suite builds on these, so when something deeper fails
this test says whether the foundation was sound. It deliberately does not care
which FPGA is fitted, so it runs on any board on any site.
"""

import pytest


@pytest.mark.live
def test_a_board_page_gives_you_a_live_camera_and_a_working_terminal(board_page, evidence):
    session = board_page()
    board, terminal, camera = session.board, session.terminal, session.camera

    detail = camera.wait_until_live(timeout=60)
    evidence.ground_truth(
        f"{board.hostname}'s camera is showing a live picture",
        True,
        detail=f"{detail}; player {camera.player_state()}",
    )

    # The terminal is a canvas, so this also proves all three readings agree:
    # the WebSocket bytes, the clipboard copy, and OCR of the pixels.
    hostname = terminal.run("hostname")
    shown, detail = hostname.shows(board.hostname)
    evidence.ground_truth(
        "the web terminal reaches the board the page says it is",
        shown,
        detail=detail,
    )

    uptime = terminal.run("uptime -p")
    shown, detail = uptime.shows("up")
    evidence.ground_truth("the Pi answers a second command", shown, detail=detail)
