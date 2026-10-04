"""A visitor on the shared terminal is a skip; a dead terminal is a failure; evidence is never hidden.

Covers the two scheduled tests, the board_page fixture (through a nested
pytest whose fakes stand in for the browser), and the skip helper.
"""

from pathlib import Path

import pytest

import tests.shared.test_board_page_basics as basics
import tests.shared.test_direct_ssh as ssh
from e2e import journeys
from e2e.evidence import EvidenceLog
from e2e.terminal import TerminalBusy
from tests.busy import skip_for_busy_terminal

pytest_plugins = ["pytester"]

BUSY = TerminalBusy("a visitor is using the terminal: 'sudo apt install pipx' is on the shell's line")
INDEX_HTML = Path(__file__).parents[2] / "fixtures" / "html" / "welland-fpgas-index-2026-10-04.html"


def _failing_evidence():
    log = EvidenceLog()
    log.claim("every board tried was working", False, detail="skipped: pi1: dead")
    return log


# -- the helper ------------------------------------------------------------------------------------------------


def test_the_helper_skips_with_the_reason_when_nothing_failed():
    with pytest.raises(pytest.skip.Exception, match="a visitor is using the terminal"):
        skip_for_busy_terminal(EvidenceLog(), BUSY)


def test_the_helper_fails_instead_of_skipping_when_evidence_already_failed():
    with pytest.raises(pytest.fail.Exception, match="every board tried was working"):
        skip_for_busy_terminal(_failing_evidence(), BUSY)


# -- the two scheduled tests -------------------------------------------------------------------------------------


def _stub(monkeypatch, name, effect):
    def fake(*_args, **_kwargs):
        if effect is not None:
            raise effect

    monkeypatch.setattr(journeys, name, fake)


def _run_basics(monkeypatch, terminal_effect, evidence=None):
    _stub(monkeypatch, "camera_is_live", None)
    _stub(monkeypatch, "terminal_reaches_the_board", terminal_effect)
    basics.test_a_board_page_gives_you_a_live_camera_and_a_working_terminal(
        lambda: object(), evidence or EvidenceLog()
    )


def _run_ssh(monkeypatch, effect, evidence=None):
    _stub(monkeypatch, "direct_ssh_works", effect)
    ssh.test_ssh_instructions_on_the_page_let_you_log_in(lambda: object(), evidence or EvidenceLog(), None)


@pytest.mark.parametrize("run", [_run_basics, _run_ssh])
def test_a_busy_terminal_skips_the_scheduled_test(monkeypatch, run):
    with pytest.raises(pytest.skip.Exception, match="a visitor is using the terminal"):
        run(monkeypatch, BUSY)


@pytest.mark.parametrize("run", [_run_basics, _run_ssh])
def test_a_dead_terminal_still_fails_the_scheduled_test(monkeypatch, run):
    """A ground-truth failure is an AssertionError out of the journey; it must not be turned into a skip."""
    with pytest.raises(AssertionError, match="the web terminal reaches a shell prompt"):
        run(monkeypatch, AssertionError("the web terminal reaches a shell prompt"))


@pytest.mark.parametrize("run", [_run_basics, _run_ssh])
def test_a_busy_terminal_does_not_hide_evidence_that_already_failed(monkeypatch, run):
    with pytest.raises(pytest.fail.Exception, match="did not hold"):
        run(monkeypatch, BUSY, _failing_evidence())


# -- the board_page fixture --------------------------------------------------------------------------------------

CONFTEST = '''
from pathlib import Path

import pytest

import tests.shared.conftest as shared
from e2e.evidence import EvidenceLog
from e2e.picker import OnDead
from e2e.terminal import TerminalBusy
from tests.shared.conftest import board_page  # noqa: F401

HTML = Path({index!r}).read_text()


class Page:
    def goto(self, *args, **kwargs):
        pass

    def content(self):
        return HTML


class Terminal:
    def wait_for_prompt(self, timeout=60):
        raise {raises}


class Session:
    def __init__(self, board):
        self.board = board
        self.terminal = Terminal()

    def snapshot(self, path):
        pass

    def close(self):
        pass


shared.open_board = lambda browser, args, site, board: Session(board)


@pytest.fixture
def evidence():
    log = EvidenceLog()
    {preload}
    return log


@pytest.fixture
def browser(): return None
@pytest.fixture
def browser_context_args(): return {{}}
@pytest.fixture
def browser_identity(): return ""
@pytest.fixture
def page(): return Page()
@pytest.fixture
def site():
    class S:
        index_url = "x"
    return S()
@pytest.fixture
def seed(): return 1
@pytest.fixture
def on_dead(): return OnDead.FAIL
@pytest.fixture
def output_dir(tmp_path): return tmp_path
'''


def _nested(pytester, raises, preload="pass"):
    pytester.makeconftest(CONFTEST.format(index=str(INDEX_HTML), raises=raises, preload=preload))
    pytester.makepyfile("def test_it(board_page):\n    board_page()\n")
    return pytester.runpytest("-p", "no:playwright", "-rs")


def test_a_visitor_typing_when_the_fixture_looks_skips_the_test_with_the_reason(pytester):
    result = _nested(pytester, "TerminalBusy('a visitor is using the terminal: it is typing')")
    result.assert_outcomes(skipped=1)
    result.stdout.fnmatch_lines(["SKIPPED*a visitor is using the terminal: it is typing"])


def test_a_terminal_with_no_prompt_still_fails_the_test_in_the_fixture(pytester):
    result = _nested(pytester, "TimeoutError('no shell prompt within 45s')")
    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines(["*no usable board*", "*the web terminal never reached a prompt*"])


def test_a_visitor_typing_does_not_hide_evidence_that_already_failed_in_the_fixture(pytester):
    result = _nested(
        pytester,
        "TerminalBusy('a visitor is using the terminal: it is typing')",
        preload="log.claim('every board tried was working', False, detail='pi1: dead')",
    )
    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines(["*every board tried was working*"])
