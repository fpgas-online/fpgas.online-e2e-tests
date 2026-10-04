"""Known failures: strict, per site, narrowed to "the ssh port could not be reached", and the table cannot rot.

Nested pytest runs whose conftest reuses the suite's own hooks and fixtures
(tests/conftest.py, including the evidence check that runs after every live
test) with a table of their own. The nested test calls the real shared test
with the real journey and the real ssh client, with the browser and the
pseudo-terminal stood in for.
"""

from pathlib import Path

import pytest

from e2e import known_failures, sshclient
from e2e.journeys import SshPortUnreachable

pytest_plugins = ["pytester"]

ISSUE = "https://github.com/fpgas-online/fpgas.online-infra/issues/191"
REPO = Path(__file__).parents[2]
REAL = "test_ssh_instructions_on_the_page_let_you_log_in"

CONFTEST = """
import pathlib

import pytest

from e2e import known_failures
from e2e.journeys import SshPortUnreachable
from tests.conftest import (  # noqa: F401
    _require_ground_truth,
    evidence,
    pytest_addoption,
    pytest_collection_modifyitems,
    pytest_runtest_makereport,
)

_saved = known_failures.ROOT, known_failures.KNOWN_FAILURES


def pytest_unconfigure(config):
    known_failures.ROOT, known_failures.KNOWN_FAILURES = _saved


known_failures.ROOT = pathlib.Path(__file__).parent
known_failures.KNOWN_FAILURES = {{
    ("welland", "test_ssh.py::{real}"): known_failures.KnownFailure(
        reason="unreachable, tracked in {issue}", raises=SshPortUnreachable
    ),
    {extra}
}}


class Board:
    hostname = "pi-sw2-p46"


class Page:
    def inner_text(self, selector):
        return "user: pi, host: welland.fpgas.online, port 23722\\nssh -p 23722 pi@welland.fpgas.online"


class Session:
    board = Board()
    page = Page()


@pytest.fixture
def board_page():
    {board_page}


@pytest.fixture
def known_hosts(tmp_path):
    return tmp_path / "known_hosts"
"""

TEST = """
import pytest

import tests.shared.test_direct_ssh as real
from e2e import journeys, sshclient
from e2e.terminal import TerminalBusy


class Login:
    banner = "x"

    def __init__(self, hostname):
        self.outputs = {{"hostname": hostname}}


class Child:
    '''A pexpect child that is ssh as far as sshclient can tell.'''

    def __init__(self, index, before, after=""):
        self.index, self.before, self.after = index, before, after

    def expect(self, patterns, **kwargs):
        return self.index

    def sendline(self, line):
        pass

    def read_nonblocking(self, size=4096, timeout=0.5):
        raise sshclient.pexpect.TIMEOUT("nothing more")

    def close(self, force=False):
        pass


def _fake_login(monkeypatch, outcome):
    def login(command, commands, known_hosts, timeout=30.0):
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    monkeypatch.setattr(journeys, "log_in_with_the_printed_command", login)


def _fake_ssh(monkeypatch, child):
    real_login = sshclient.log_in_with_the_printed_command
    monkeypatch.setattr(sshclient.pexpect, "spawn", lambda *args, **kwargs: child)
    monkeypatch.setattr(
        journeys,
        "log_in_with_the_printed_command",
        lambda c, cmds, kh, timeout=30.0: real_login(c, cmds, kh, timeout=1),
    )


@pytest.mark.live
def {real}(monkeypatch, board_page, evidence, known_hosts):
    {setup}
    real.{real}(board_page, evidence, known_hosts)
"""

REFUSED = "SshUnreachable('refused')"
PASSWORD_PROMPT = 1
EOF_ = 2
TIMEOUT = 3


def _run(pytester, site, setup, extra="", board_page="return lambda: Session()"):
    pytester.makeconftest(CONFTEST.format(real=REAL, issue=ISSUE, extra=extra, board_page=board_page))
    pytester.makeini("[pytest]\naddopts = -ra --strict-markers\nmarkers =\n    live: x\n    claim_only: x\n")
    test = TEST.format(real=REAL, setup=setup)
    pytester.makepyfile(
        test_ssh=test.replace("from e2e.terminal", "from e2e.sshclient import SshUnreachable\nfrom e2e.terminal")
    )
    return pytester.runpytest("--site", site, "-p", "no:playwright")


def _child(index, before, after=""):
    return (index, before, after)


def _setup(case):
    return f"_fake_ssh(monkeypatch, Child{case!r})"


# What ssh prints, one case per way the login can fail. The first group is "the port could not be reached".
UNREACHABLE = {
    "refused": _child(EOF_, "ssh: connect to host welland.fpgas.online port 23722: Connection refused\r\n"),
    "timed out": _child(EOF_, "ssh: connect to host welland.fpgas.online port 23722: Connection timed out\r\n"),
    "no route": _child(EOF_, "ssh: connect to host welland.fpgas.online port 23722: No route to host\r\n"),
    "silence": _child(TIMEOUT, ""),
}
REACHED = {
    "dns failure": _child(EOF_, "ssh: Could not resolve hostname welland.fpgas.online: Name or service not known\r\n"),
    "publickey only": _child(EOF_, "pi@welland.fpgas.online: Permission denied (publickey).\r\n"),
    "no matching algorithm": _child(
        EOF_, "Unable to negotiate with 1.2.3.4 port 23722: no matching key exchange method\r\n"
    ),
    "closed after the banner": _child(EOF_, "Welcome\r\nConnection closed by 1.2.3.4 port 23722\r\n"),
    "silent after some output": _child(TIMEOUT, "Welcome to the board\r\n"),
    "banner without a password": _child(
        PASSWORD_PROMPT,
        "This is a long notice that contains no credential at all.\r\npi@welland.fpgas.online's ",
        "password:",
    ),
    "password typed, no prompt": _child(PASSWORD_PROMPT, "ship7ohT\r\npi@welland.fpgas.online's ", "password:"),
}


@pytest.mark.parametrize("case", sorted(UNREACHABLE))
def test_on_welland_a_port_that_cannot_be_reached_is_xfailed_with_the_issue_url(pytester, case):
    result = _run(pytester, "welland", _setup(UNREACHABLE[case]))
    result.assert_outcomes(xfailed=1)
    result.stdout.fnmatch_lines([f"XFAIL*{ISSUE}*"])


@pytest.mark.parametrize("case", sorted(REACHED))
def test_on_welland_every_other_ssh_failure_still_fails(pytester, case):
    result = _run(pytester, "welland", _setup(REACHED[case]))
    result.assert_outcomes(failed=1)
    # failed for the reason under test, not because the stand-ins broke
    result.stdout.fnmatch_lines(["*logs in with the banner's password*"])


@pytest.mark.parametrize("case", sorted(UNREACHABLE))
def test_on_ps1_the_same_unreachable_port_fails_normally(pytester, case):
    result = _run(pytester, "ps1", _setup(UNREACHABLE[case]))
    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines(["*SshPortUnreachable*"])


def test_on_welland_a_login_that_works_fails_the_run_strictly(pytester):
    result = _run(pytester, "welland", '_fake_login(monkeypatch, Login("pi-sw2-p46"))')
    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines(["*XPASS(strict)*"])


def test_on_welland_a_login_to_the_wrong_board_still_fails(pytester):
    result = _run(pytester, "welland", '_fake_login(monkeypatch, Login("some-other-pi"))')
    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines(["*ssh reached the board the page said it would*"])


@pytest.mark.parametrize("error", ["RuntimeError('the page did not open')", "ValueError('not an ssh command')"])
def test_on_welland_any_other_error_still_fails(pytester, error):
    result = _run(pytester, "welland", f"_fake_login(monkeypatch, {error})")
    result.assert_outcomes(failed=1)


def test_on_welland_a_setup_fixture_error_stays_an_error_not_an_expected_failure(pytester):
    result = _run(
        pytester,
        "welland",
        "pass",
        board_page="raise RuntimeError('no usable board: the camera feed never went live')",
    )
    result.assert_outcomes(errors=1)
    result.stdout.fnmatch_lines(["*no usable board*"])


def test_on_welland_a_busy_terminal_stays_a_skip(pytester):
    result = _run(
        pytester,
        "welland",
        "_fake_login(monkeypatch, TerminalBusy('a visitor is using the terminal: it is typing'))",
    )
    result.assert_outcomes(skipped=1)


def test_a_table_entry_naming_a_test_that_does_not_exist_is_an_error(pytester):
    extra = '("welland", "test_ssh.py::test_gone"): known_failures.KnownFailure(reason="x", raises=SshPortUnreachable),'
    result = _run(pytester, "welland", "pass", extra=extra)
    assert result.ret != 0
    assert "test_ssh.py::test_gone" in result.stdout.str() + result.stderr.str()
    result.assert_outcomes()


# -- how the ssh client tells "could not reach the port" from everything else ----------------------------------


@pytest.mark.parametrize("case", sorted(UNREACHABLE))
def test_the_client_raises_unreachable_only_for_the_port_not_being_reached(monkeypatch, tmp_path, case):
    child = _Child(*UNREACHABLE[case])
    monkeypatch.setattr(sshclient.pexpect, "spawn", lambda *args, **kwargs: child)
    with pytest.raises(sshclient.SshUnreachable):
        sshclient.log_in_with_the_printed_command(
            "ssh -p 23722 pi@welland.fpgas.online", ["hostname"], tmp_path / "kh", timeout=1
        )


@pytest.mark.parametrize(
    "case",
    ["dns failure", "publickey only", "no matching algorithm", "closed after the banner", "silent after some output"],
)
def test_the_client_raises_a_plain_failure_once_the_port_was_reached(monkeypatch, tmp_path, case):
    child = _Child(*REACHED[case])
    monkeypatch.setattr(sshclient.pexpect, "spawn", lambda *args, **kwargs: child)
    with pytest.raises(sshclient.SshFailed) as caught:
        sshclient.log_in_with_the_printed_command(
            "ssh -p 23722 pi@welland.fpgas.online", ["hostname"], tmp_path / "kh", timeout=1
        )
    assert not isinstance(caught.value, sshclient.SshUnreachable)


class _Child:
    def __init__(self, index, before, after=""):
        self.index, self.before, self.after = index, before, after

    def expect(self, patterns, **kwargs):
        return self.index

    def read_nonblocking(self, size=4096, timeout=0.5):
        raise sshclient.pexpect.TIMEOUT("nothing more")

    def close(self, force=False):
        pass


# -- the table ---------------------------------------------------------------------------------------------------


def test_the_real_table_names_real_tests_and_the_issue_url():
    known_failures.validate(known_failures.KNOWN_FAILURES, REPO)
    for (site, _test), entry in known_failures.KNOWN_FAILURES.items():
        assert site in {"welland", "ps1"}
        assert "https://github.com/" in entry.reason


def test_the_real_table_has_the_welland_ssh_entry_only_for_welland_and_only_for_an_unreachable_port():
    key = f"tests/shared/test_direct_ssh.py::{REAL}"
    entry = known_failures.KNOWN_FAILURES[("welland", key)]
    assert ISSUE in entry.reason
    assert entry.raises is SshPortUnreachable
    assert ("ps1", key) not in known_failures.KNOWN_FAILURES


def test_the_marker_exception_is_an_assertion_error_so_nothing_else_about_the_journey_changes():
    assert issubclass(SshPortUnreachable, AssertionError)
    assert issubclass(sshclient.SshUnreachable, sshclient.SshFailed)
