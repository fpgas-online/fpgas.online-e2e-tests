"""Do the ssh instructions printed on the board page actually work?

The page prints `ssh -p 23722 pi@welland.fpgas.online` and says the password
is in the login banner. A person copies that command into a terminal, answers
the first-connection question, reads the banner, types the password and gets
a shell. So does this test, with the real ssh client. The ground truth is a
shell on the Pi that agrees with the page about which board it is.
"""

import pytest

from e2e import journeys


@pytest.mark.live
def test_ssh_instructions_on_the_page_let_you_log_in(board_page, evidence, known_hosts):
    session = board_page()
    journeys.direct_ssh_works(session, evidence, known_hosts)
