"""The two things a board page has to give you before anything else matters:
a terminal you can type in, and a camera you can watch.

Every other test in the suite builds on these, so when something deeper fails
this test says whether the foundation was sound. It deliberately does not care
which FPGA is fitted, so it runs on any board on any site.
"""

import pytest

from e2e import journeys


@pytest.mark.live
def test_a_board_page_gives_you_a_live_camera_and_a_working_terminal(board_page, evidence):
    session = board_page()
    journeys.camera_is_live(session, evidence)
    journeys.terminal_reaches_the_board(session, evidence)
