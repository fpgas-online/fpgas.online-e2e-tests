"""Can a person upload a bitstream through the form and see it running?

The claim is the success page. The ground truth is that the file really landed
on the Pi at the right size and just now, that openFPGALoader really programmed
the part, and that the LEDs visibly changed and are now moving.
"""

import pytest

from e2e import journeys


@pytest.mark.live
def test_uploaded_bitstream_programs_the_arty_and_changes_the_leds(board_page, evidence):
    session = board_page()
    journeys.upload_programs_the_board(session, evidence)
