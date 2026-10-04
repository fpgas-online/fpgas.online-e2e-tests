"""Known failures: strict, per site, narrowed to the one expected failure, and the table cannot rot.

Nested pytest runs whose conftest reuses the suite's own hook (tests/conftest.py)
with a table of their own, and a test that calls the real journey with the ssh
client and the page stood in for.
"""

from pathlib import Path

import pytest

from e2e import known_failures
from e2e.journeys import SshNoLogin

pytest_plugins = ["pytester"]

ISSUE = "https://github.com/fpgas-online/fpgas.online-infra/issues/191"
REPO = Path(__file__).parents[2]

CONFTEST = """
from e2e import known_failures
from e2e.journeys import SshNoLogin
from tests.conftest import pytest_addoption, pytest_collection_modifyitems  # noqa: F401

_saved = known_failures.ROOT, known_failures.KNOWN_FAILURES


def pytest_unconfigure(config):
    known_failures.ROOT, known_failures.KNOWN_FAILURES = _saved


known_failures.ROOT = __import__("pathlib").Path(__file__).parent
known_failures.KNOWN_FAILURES = {{
    ("welland", "test_ssh.py::test_ssh_login"): known_failures.KnownFailure(
        reason="no login, tracked in {issue}", raises=SshNoLogin
    ),
    {extra}
}}
"""

TEST = """
import pytest

from e2e import journeys
from e2e.evidence import EvidenceLog
from e2e.sshclient import SshFailed

PAGE = "user: pi, host: welland.fpgas.online, port 23722\\nssh -p 23722 pi@welland.fpgas.online"


class Board:
    hostname = "pi-sw2-p46"


class Page:
    def inner_text(self, selector):
        return PAGE


class Session:
    board = Board()
    page = Page()


def fake_login(outcome):
    def login(command, commands, known_hosts, timeout=30.0):
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome
    return login


class Login:
    banner = "x"
    def __init__(self, hostname):
        self.outputs = {{"hostname": hostname}}


@pytest.mark.parametrize("n", [0])
def test_ssh_login(monkeypatch, n):
    monkeypatch.setattr(journeys, "log_in_with_the_printed_command", fake_login({outcome}))
    journeys.direct_ssh_works(Session(), EvidenceLog(), None)
"""


def _run(pytester, site, outcome, extra=""):
    pytester.makeconftest(CONFTEST.format(issue=ISSUE, extra=extra))
    pytester.makeini("[pytest]\naddopts = -ra --strict-markers\n")
    pytester.makepyfile(test_ssh=TEST.format(outcome=outcome))
    return pytester.runpytest("--site", site, "-p", "no:playwright")


NO_LOGIN = "SshFailed(\"exited before asking for a password; it printed 'Connection refused'\")"


def test_on_welland_the_no_login_failure_is_reported_xfailed_with_the_issue_url(pytester):
    result = _run(pytester, "welland", NO_LOGIN)
    result.assert_outcomes(xfailed=1)
    result.stdout.fnmatch_lines([f"XFAIL*{ISSUE}*"])


def test_on_welland_a_login_that_works_fails_the_run_strictly(pytester):
    result = _run(pytester, "welland", 'Login("pi-sw2-p46")')
    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines(["*XPASS(strict)*"])


def test_on_welland_a_login_to_the_wrong_board_still_fails(pytester):
    result = _run(pytester, "welland", 'Login("some-other-pi")')
    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines(["*ssh reached the board the page said it would*"])


@pytest.mark.parametrize("outcome", ['RuntimeError("the page did not open")', 'ValueError("not an ssh command")'])
def test_on_welland_any_other_error_still_fails(pytester, outcome):
    result = _run(pytester, "welland", outcome)
    result.assert_outcomes(failed=1)


def test_on_ps1_the_same_no_login_failure_fails_normally(pytester):
    result = _run(pytester, "ps1", NO_LOGIN)
    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines(["*SshNoLogin*"])


def test_a_table_entry_naming_a_test_that_does_not_exist_is_an_error(pytester):
    extra = '("welland", "test_ssh.py::test_gone"): known_failures.KnownFailure(reason="x", raises=SshNoLogin),'
    result = _run(pytester, "welland", NO_LOGIN, extra=extra)
    assert result.ret != 0
    assert "test_ssh.py::test_gone" in result.stdout.str() + result.stderr.str()
    result.assert_outcomes()


def test_the_real_table_names_real_tests_and_the_issue_url():
    known_failures.validate(known_failures.KNOWN_FAILURES, REPO)
    for (site, _test), entry in known_failures.KNOWN_FAILURES.items():
        assert site in {"welland", "ps1"}
        assert ISSUE in entry.reason or "https://github.com/" in entry.reason


def test_the_real_table_has_the_welland_ssh_entry_only_for_welland_and_only_for_no_login():
    key = "tests/shared/test_direct_ssh.py::test_ssh_instructions_on_the_page_let_you_log_in"
    entry = known_failures.KNOWN_FAILURES[("welland", key)]
    assert ISSUE in entry.reason
    assert entry.raises is SshNoLogin
    assert ("ps1", key) not in known_failures.KNOWN_FAILURES


def test_no_login_is_an_assertion_error_so_nothing_else_about_the_journey_changes():
    assert issubclass(SshNoLogin, AssertionError)
