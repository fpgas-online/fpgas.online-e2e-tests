"""The direct-ssh journey reads the page's `ssh -4 -p` command and checks it against the page (#19).

Since fpgas.online-site #63 the board page prints `ssh -4 -p <port> pi@<site>`;
the old pattern read an empty command from it and the scheduled runs failed.
The ssh client itself is stubbed: what is under test is what the journey reads
off the page and what it hands the client.
"""

from types import SimpleNamespace

from e2e import journeys
from e2e.board import Board
from e2e.evidence import EvidenceLog
from tests.unit.test_sshbanner import PAGE_DASH4


class _Page:
    def __init__(self, text):
        self.text = text

    def inner_text(self, selector):
        assert selector == "body"
        return self.text


def _run(monkeypatch, page_text, hostname="pi-sw2-p44"):
    handed = []

    def fake_login(command, commands, known_hosts, timeout):
        handed.append(command)
        return SimpleNamespace(banner="example1\n", outputs={"hostname": hostname + "\n"})

    monkeypatch.setattr(journeys, "log_in_with_the_printed_command", fake_login)
    session = SimpleNamespace(board=Board(hostname, 44, "Arty"), page=_Page(page_text))
    log = EvidenceLog()
    journeys.direct_ssh_works(session, log, known_hosts=None)
    return log, handed


def test_the_dash_4_command_is_read_and_run(monkeypatch):
    log, handed = _run(monkeypatch, PAGE_DASH4)
    assert handed == ["ssh -4 -p 24422 pi@welland.fpgas.online"]
    assert log.failures == []


def test_a_command_that_disagrees_with_the_stated_port_is_a_failed_claim(monkeypatch):
    page = PAGE_DASH4.replace("ssh -4 -p 24422", "ssh -4 -p 24423")
    log, _ = _run(monkeypatch, page)
    assert [e.description for e in log.failures] == [
        "the printed command uses the port, user and host the page states"]
