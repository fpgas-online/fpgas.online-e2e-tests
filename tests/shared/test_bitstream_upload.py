"""Can a person upload a bitstream through the form and see it running?

The claim is the success page. The ground truth is that the file really landed
on the Pi at the right size and just now, that openFPGALoader really programmed
the part, and that the LEDs visibly changed and are now moving.

What is loaded, and how, comes from the FPGA type the site shows for the board
(journeys.LOADABLE); a type with no bitstream in this repo (every Acorn today)
skips the test rather than guessing.
"""

import pytest

from e2e import journeys


@pytest.mark.live
def test_uploaded_bitstream_programs_the_fpga_and_changes_the_leds(board_page, evidence):
    session = board_page()
    if journeys.loadable_for(session.board) is None:
        pytest.skip(journeys.no_bitstream_reason(session.board))
    journeys.upload_programs_the_board(session, evidence)
