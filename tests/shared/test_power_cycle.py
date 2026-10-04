"""Does 'turn it off and on again' actually turn the board off and on again?

The claim is the status box. The ground truth is that the camera stops seeing
a live picture -- the camera runs on the Pi, so the feed dying IS the Pi
dying -- and that the Pi's own uptime went backwards afterwards.
"""

import pytest

from e2e import journeys


@pytest.mark.live
def test_reset_button_power_cycles_the_board(board_page, evidence):
    session = board_page()
    journeys.reset_power_cycles_the_board(session, evidence)
