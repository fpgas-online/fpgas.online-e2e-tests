"""Which boards a run may touch: named explicitly, never protected, and nothing else opened.

The registry pages are fixtures: the site's /fleet/ page of 2026-10-04, and the
same page with the protected device's hostname changed, which is what a board
re-patched or renamed looks like to a run.
"""

from pathlib import Path

import pytest

from e2e import audit, journeys, protection
from e2e.board import Board
from e2e.picker import NoSuchBoard, choose
from e2e.protection import (
    DisruptionGuard,
    RegistryError,
    disruption_refusal,
    load_protected,
    parse_registry,
    read_registry,
    require_named_boards,
)
from e2e.site import Site, parse_boards

pytest_plugins = ["pytester"]

HTML = Path(__file__).parents[2] / "fixtures" / "html"
FLEET = (HTML / "welland-fleet-2026-10-04.html").read_text()
SERIAL = "285df3f84af242d0"
SITE = Site("welland", "https://welland.fpgas.online")


def _board(hostname):
    return Board(hostname, 1, "")


def _hostname_of(serial, html=FLEET):
    return {s: h for h, s in parse_registry(html).items()}[serial]


# -- the protected list and the registry --------------------------------------------------------------------------


def test_the_protected_list_names_the_device_by_serial_with_label_and_reason():
    entry = load_protected()[SERIAL]
    assert entry.label == "acorn-holly"
    assert entry.reason == "Acorn reference board: kept in a known state for comparisons"


def test_a_protected_entry_missing_its_reason_is_an_error_not_a_shorter_list(tmp_path):
    path = tmp_path / "p.toml"
    path.write_text('[[protected]]\nserial = "1"\nlabel = "x"\n')
    with pytest.raises(ValueError, match="reason"):
        load_protected(path)


def test_the_registry_page_gives_each_hostname_its_serial():
    registry = parse_registry(FLEET)
    assert registry[_hostname_of(SERIAL)] == SERIAL
    assert all(len(serial) == 16 for serial in registry.values())


@pytest.mark.parametrize(
    "html",
    [
        "<html><body><table><tr><th>Hostname</th></tr></table></body></html>",
        "<table><tr><td colspan=8>No machines have registered yet.</td></tr></table>",
        "",
    ],
)
def test_a_registry_with_no_machines_is_an_error(html):
    with pytest.raises(RegistryError, match="no machines"):
        parse_registry(html)


def test_one_hostname_with_two_serials_is_an_error():
    html = "<table><tr><td>a</td><td>s</td><td>0001</td></tr><tr><td>a</td><td>s</td><td>0002</td></tr></table>"
    with pytest.raises(RegistryError, match="two serials"):
        parse_registry(html)


# -- refusing the protected device ----------------------------------------------------------------------------------


def test_the_protected_device_is_refused_naming_its_label_and_reason_even_when_named():
    registry, protected = parse_registry(FLEET), load_protected()
    why = disruption_refusal(_board(_hostname_of(SERIAL)), registry, protected)
    assert "acorn-holly" in why and "known state for comparisons" in why


def test_another_board_may_be_disrupted():
    registry, protected = parse_registry(FLEET), load_protected()
    other = next(h for h, s in registry.items() if s != SERIAL)
    assert disruption_refusal(_board(other), registry, protected) == ""


def test_the_protected_device_is_still_refused_when_it_answers_to_another_hostname():
    """Identity is the serial, read at run time: renaming or re-patching the board does not unprotect it."""
    old = _hostname_of(SERIAL)
    moved = FLEET.replace(f">{old}<", ">pi-sw9-p99<")
    assert old not in parse_registry(moved)
    guard = DisruptionGuard(SITE, fetch=lambda _url: moved)
    assert "acorn-holly" in guard.refusal(_board("pi-sw9-p99"))
    assert "identity is unknown" in guard.refusal(_board(old))  # the old name now names nothing


def test_a_board_the_registry_does_not_list_is_refused_as_unknown():
    guard = DisruptionGuard(SITE, fetch=lambda _url: FLEET)
    assert "identity is unknown" in guard.refusal(_board("no-such-board"))


def test_an_unreadable_registry_refuses_every_board_with_the_reason():
    def down(_url):
        raise OSError("connection refused")

    guard = DisruptionGuard(SITE, fetch=down)
    why = guard.refusal(_board("pi-sw2-p46"))
    assert "could not be read" in why and "connection refused" in why and "pi-sw2-p46" in why


def test_the_registry_is_read_once_per_run():
    reads = []
    guard = DisruptionGuard(SITE, fetch=lambda url: reads.append(url) or FLEET)
    guard.refusal(_board("a"))
    guard.refusal(_board("b"))
    assert reads == ["https://welland.fpgas.online/fleet/"]


def test_the_registry_is_read_from_the_sites_public_fleet_page():
    assert read_registry(SITE, fetch=lambda url: FLEET if url.endswith("/fleet/") else "")


def test_the_real_disruption_guard_reads_the_protected_file():
    assert DisruptionGuard(SITE, fetch=lambda _u: FLEET).protected == load_protected(protection.PROTECTED_FILE)


# -- --boards and --disruptive ------------------------------------------------------------------


def test_disruptive_needs_named_boards():
    with pytest.raises(ValueError, match="--disruptive needs --boards"):
        require_named_boards(True, set())
    require_named_boards(True, {"pi-sw2-p46"})
    require_named_boards(False, set())


BOARDS = [Board("pi-sw2-p16", 16, ""), Board("pi-sw2-p29", 29, ""), Board("pi-sw2-p37", 37, "")]


def test_choose_picks_only_among_the_named_boards_that_are_listed():
    for seed in range(10):
        assert {b.hostname for b in choose(BOARDS, seed, wanted={"pi-sw2-p29", "pi-sw2-p99"})} == {"pi-sw2-p29"}


def test_choose_fails_naming_the_boards_when_none_of_them_is_listed():
    with pytest.raises(NoSuchBoard, match="pi-sw2-p99"):
        choose(BOARDS, 1, wanted={"pi-sw2-p99"})


# -- the audit's disruptive cells -----------------------------------------------------------


class _Session:
    board = Board("pi-sw2-p47", 47, "")


def _audit(monkeypatch, **kwargs):
    ran = []

    def fake(name, *_a, **_k):
        ran.append(name)
        return audit.Check(name=name, passed=True, detail="ok")

    monkeypatch.setattr(audit, "run_journey", fake)
    monkeypatch.setattr(journeys, "loadable_for", lambda _board: ("top.bit", []))
    return audit.audit_board(_Session(), None, **kwargs), ran


def test_a_refused_board_fails_its_disruptive_cells_and_runs_neither(monkeypatch):
    row, ran = _audit(monkeypatch, disruptive=True, refusal="pi-sw2-p47 is the protected device acorn-holly: x")
    assert "upload" not in ran and "power cycle" not in ran and "camera" in ran
    for name in ("upload", "power cycle"):
        check = row.check(name)
        assert not check.passed and not check.skipped and check.detail.startswith("refused: ")
        assert "acorn-holly" in check.detail


def test_a_board_that_may_be_disrupted_runs_its_disruptive_cells(monkeypatch):
    _, ran = _audit(monkeypatch, disruptive=True, refusal="")
    assert "upload" in ran and "power cycle" in ran


def test_without_disruptive_a_refusal_changes_nothing_the_cells_stay_skipped(monkeypatch):
    row, ran = _audit(monkeypatch, disruptive=False, refusal="")
    assert row.check("upload").skipped and "upload" not in ran


# -- the shared tests' board_page fixture, with the browser faked ---------------------------------

CONFTEST = '''
from pathlib import Path

import pytest

import tests.shared.conftest as shared
from e2e.evidence import EvidenceLog
from e2e.picker import OnDead
from e2e.protection import DisruptionGuard
from e2e.site import Site
from tests.shared.conftest import board_page  # noqa: F401

INDEX = Path({index!r}).read_text()
FLEET = Path({fleet!r}).read_text()
OPENED = Path({opened!r})


class Page:
    def goto(self, *a, **k): pass
    def content(self): return INDEX


class Terminal:
    def wait_for_prompt(self, timeout=60): pass


class Camera:
    def check_live_with_recovery(self, timeout=60): return True, "ticking"


class Session:
    def __init__(self, board):
        self.board, self.terminal, self.camera = board, Terminal(), Camera()
    def snapshot(self, path): pass
    def close(self): pass


def fake_open_board(browser, args, site, board):
    OPENED.write_text(OPENED.read_text() + board.hostname + "\\n" if OPENED.exists() else board.hostname + "\\n")
    return Session(board)


shared.open_board = fake_open_board


@pytest.fixture
def evidence(): return EvidenceLog()
@pytest.fixture
def browser(): return None
@pytest.fixture
def browser_context_args(): return {{}}
@pytest.fixture
def browser_identity(): return ""
@pytest.fixture
def page(): return Page()
@pytest.fixture
def site(): return Site("welland", "https://welland.fpgas.online")
@pytest.fixture
def seed(request): return int(request.config.getoption("--seed-for-test"))
@pytest.fixture
def on_dead(): return OnDead.FAIL
@pytest.fixture
def output_dir(tmp_path): return tmp_path
@pytest.fixture
def boards_wanted(request):
    return {{n for n in request.config.getoption("--boards-for-test").split(",") if n}}
@pytest.fixture
def disruption_guard(site): return DisruptionGuard(site, fetch=lambda url: FLEET)


def pytest_addoption(parser):
    parser.addoption("--seed-for-test", default="1")
    parser.addoption("--boards-for-test", default="")
'''

TEST = """
import pytest

def test_plain(board_page):
    board_page()

@pytest.mark.disruptive
def test_disruptive(board_page):
    board_page()
"""


def _nested(pytester, *args, select):
    opened = pytester.path / "opened.txt"
    pytester.makeconftest(
        CONFTEST.format(
            index=str(HTML / "welland-fpgas-index-2026-10-04.html"),
            fleet=str(HTML / "welland-fleet-2026-10-04.html"),
            opened=str(opened),
        )
    )
    pytester.makeini("[pytest]\nmarkers =\n    disruptive: x\naddopts = --strict-markers\n")
    pytester.makepyfile(TEST)
    result = pytester.runpytest("-p", "no:playwright", "-k", select, *args)
    return result, (opened.read_text().split() if opened.exists() else [])


def _listed():
    return [b.hostname for b in parse_boards((HTML / "welland-fpgas-index-2026-10-04.html").read_text())]


def test_a_shared_test_with_boards_opens_only_the_named_board_whatever_the_seed(pytester):
    named = "pi-sw2-p46"
    assert set(_listed()) == {named, _hostname_of(SERIAL)}  # the other listed board comes first under some seeds
    for seed in range(8):
        result, opened = _nested(pytester, f"--seed-for-test={seed}", f"--boards-for-test={named}", select="test_plain")
        result.assert_outcomes(passed=1)
        assert opened == [named]
        (pytester.path / "opened.txt").unlink()


def test_a_shared_test_with_boards_none_of_which_is_listed_fails_naming_them_and_opens_nothing(pytester):
    result, opened = _nested(pytester, "--boards-for-test=pi-sw9-p99", select="test_plain")
    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines(["*pi-sw9-p99*"])
    assert opened == []


def test_a_disruptive_test_without_boards_fails_and_opens_nothing(pytester):
    result, opened = _nested(pytester, select="test_disruptive")
    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines(["*never chooses its board*"])
    assert opened == []


def test_a_disruptive_test_on_the_protected_board_named_explicitly_is_refused_before_it_opens(pytester):
    result, opened = _nested(pytester, f"--boards-for-test={_hostname_of(SERIAL)}", select="test_disruptive")
    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines(["*refused*acorn-holly*"])
    assert opened == []


def test_a_disruptive_test_on_another_named_board_runs_on_it(pytester):
    other = next(h for h in _listed() if h != _hostname_of(SERIAL) and h in parse_registry(FLEET))
    result, opened = _nested(pytester, f"--boards-for-test={other}", select="test_disruptive")
    result.assert_outcomes(passed=1)
    assert opened == [other]


def test_a_non_disruptive_test_may_use_the_protected_board_as_a_visitor_does(pytester):
    protected = _hostname_of(SERIAL)
    result, opened = _nested(pytester, f"--boards-for-test={protected}", select="test_plain")
    result.assert_outcomes(passed=1)
    assert opened == [protected]
