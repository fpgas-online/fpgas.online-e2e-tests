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


class _Response:
    def __init__(self, status):
        self.status = status


class _Request:
    def get(self, url):
        return _Response(next((s for host, s in {statuses!r}.items() if host in url), 200))


class Page:
    request = _Request()

    def goto(self, *args, **kwargs):
        pass

    def content(self):
        return HTML


class Terminal:
    def wait_for_prompt(self, timeout=60):
        raise {raises}


class Camera:
    def __init__(self, board):
        self.board = board

    def check_live_with_recovery(self, timeout=60):
        if self.board.has_camera is False:
            raise AssertionError("the camera of a board with none was consulted")
        return {camera_live}, "clock did not advance"


class Session:
    def __init__(self, board):
        self.board = board
        self.terminal = Terminal()
        self.camera = Camera(board)

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
def on_dead(): return OnDead.{on_dead}
@pytest.fixture
def output_dir(tmp_path): return tmp_path
@pytest.fixture
def boards_wanted(): return {wanted!r}
@pytest.fixture
def disruption_guard(): return None
'''


def _nested(pytester, raises, preload="pass", camera_live=True, statuses=None, on_dead="FAIL", wanted=()):
    pytester.makeconftest(
        CONFTEST.format(
            index=str(INDEX_HTML),
            raises=raises,
            preload=preload,
            camera_live=camera_live,
            statuses=statuses or {},
            on_dead=on_dead,
            wanted=set(wanted),
        )
    )
    pytester.makepyfile("def test_it(board_page):\n    board_page()\n")
    return pytester.runpytest("-p", "no:playwright", "-rs", "-s")


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


@pytest.mark.parametrize("run", [_run_basics, _run_ssh])
def test_a_broken_terminal_is_never_turned_into_a_skip(monkeypatch, run):
    from e2e.terminal import TerminalLost

    with pytest.raises(TerminalLost):
        run(monkeypatch, TerminalLost("the shell's line is broken ('Stale file handle')"))


def test_a_dead_camera_fails_even_when_the_terminal_is_busy(pytester):
    """The camera is checked first, so a busy terminal cannot hide a board with no picture."""
    result = _nested(
        pytester, "TerminalBusy('a visitor is using the terminal: it is typing')", camera_live=False
    )
    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines(["*no usable board*", "*the camera feed never went live*"])


def test_a_live_camera_and_a_busy_terminal_still_skip(pytester):
    result = _nested(pytester, "TerminalBusy('a visitor is using the terminal: it is typing')", camera_live=True)
    result.assert_outcomes(skipped=1)


# -- a board with no camera ----------------------------------------------------------------------------------------

READY = "TerminalBusy('a visitor is using the terminal: it is typing')"
NO_CAMERA_P46 = {"pi-sw2-p46": 404}
NO_CAMERA_BOTH = {"pi-sw2-p46": 404, "pi-sw2-p47": 404}


def test_the_fixture_picks_a_board_with_a_camera_and_says_why(pytester):
    result = _nested(pytester, READY, statuses=NO_CAMERA_P46)
    result.assert_outcomes(skipped=1)  # the busy terminal skip, reached on the camera board
    result.stdout.fnmatch_lines(["*picked pi-sw2-p47: has a camera; seed 1; 1 of 2 boards have a camera*"])
    assert "pi-sw2-p46" not in result.stdout.str().replace("pi-sw2-p46.html", "")


def test_a_board_with_no_camera_is_tested_for_the_page_and_terminal_without_a_camera_failure(pytester):
    """Both boards lack a camera: the terminal is still reached, and no camera failure is reported."""
    result = _nested(pytester, READY, statuses=NO_CAMERA_BOTH)
    result.assert_outcomes(skipped=1)
    result.stdout.fnmatch_lines(["*picked pi-sw2-p4*: has no camera, tried after the boards that have one*"])
    assert "feed never went live" not in result.stdout.str()


def test_naming_a_camera_less_board_with_boards_tests_it_and_says_so(pytester):
    result = _nested(pytester, READY, statuses=NO_CAMERA_P46, wanted={"pi-sw2-p46"})
    result.assert_outcomes(skipped=1)
    result.stdout.fnmatch_lines(["*picked pi-sw2-p46: named by --boards; has no camera; seed 1; 1 of 2 boards*"])


def test_a_dead_terminal_on_a_camera_less_board_still_fails(pytester):
    result = _nested(pytester, "TimeoutError('no shell prompt within 45s')", statuses=NO_CAMERA_BOTH)
    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines(["*the web terminal never reached a prompt*"])


def test_a_slow_camera_on_a_board_that_has_one_stays_a_failure_and_is_not_passed_over(pytester):
    """The picked board has a camera that never goes live; the camera-less board is not a way out of that."""
    result = _nested(pytester, READY, camera_live=False, statuses=NO_CAMERA_P46)
    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines(["*pi-sw2-p47 is not usable: the camera feed never went live*"])
    assert "picked pi-sw2-p46" not in result.stdout.str()


def test_with_on_dead_retry_the_camera_less_board_is_reached_only_after_the_camera_board_failed(pytester):
    result = _nested(pytester, READY, camera_live=False, statuses=NO_CAMERA_P46, on_dead="RETRY")
    out = result.stdout.str()
    assert out.index("pi-sw2-p47 is not usable") < out.index("picked pi-sw2-p46")
