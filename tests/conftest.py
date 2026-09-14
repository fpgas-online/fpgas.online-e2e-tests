"""Session-wide fixtures: CLI options, the browser, and evidence enforcement."""

from __future__ import annotations

import os
import random
from pathlib import Path

import pytest

from e2e.evidence import EvidenceLog
from e2e.picker import OnDead
from e2e.site import Site


def pytest_addoption(parser):
    parser.addoption("--site", default="welland", help="welland or ps1")
    parser.addoption("--seed", type=int, default=None, help="replay a previous run's board choice")
    parser.addoption("--on-dead", default="fail", choices=[m.value for m in OnDead])
    parser.addoption(
        "--boards",
        default="",
        help="audit only these boards, by hostname or piNN (comma separated); for development runs",
    )


@pytest.fixture(scope="session")
def site(pytestconfig) -> Site:
    return Site.from_name(pytestconfig.getoption("--site"))


@pytest.fixture(scope="session")
def seed(pytestconfig) -> int:
    chosen = pytestconfig.getoption("--seed")
    if chosen is None:
        chosen = random.randrange(2**31)
    print(f"\n[e2e] board-selection seed: {chosen}  (replay with --seed {chosen})")
    return chosen


@pytest.fixture(scope="session")
def on_dead(pytestconfig) -> OnDead:
    return OnDead(pytestconfig.getoption("--on-dead"))


@pytest.fixture(scope="session")
def boards_wanted(pytestconfig) -> set[str]:
    return {name.strip() for name in pytestconfig.getoption("--boards").split(",") if name.strip()}


@pytest.fixture(scope="session")
def output_dir(pytestconfig) -> Path:
    """Where pytest-playwright puts screenshots and videos; reports go there too."""
    path = Path(pytestconfig.getoption("--output"))
    path.mkdir(parents=True, exist_ok=True)
    return path


@pytest.fixture(scope="session")
def known_hosts(output_dir) -> Path:
    """A known_hosts for this run only, so every run meets each board for the first time.

    That is what a new visitor's ssh does, and it is what the site's
    instructions are written for. Deleted afterwards so the next run is a
    first connection too.
    """
    path = output_dir / "known_hosts"
    path.unlink(missing_ok=True)
    yield path
    path.unlink(missing_ok=True)


BROWSER_ARGS = ["--autoplay-policy=no-user-gesture-required"]


@pytest.fixture(scope="session")
def browser_type_launch_args(browser_type_launch_args):
    """Let the video actually play; optionally use a browser of your choosing."""
    args = {
        **browser_type_launch_args,
        "args": [*browser_type_launch_args.get("args", []), *BROWSER_ARGS],
    }
    override = os.environ.get("CHROMIUM")
    if override:
        args["executable_path"] = override
    return args


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    """Grant clipboard access: copying the terminal is one of the three readings."""
    return {
        **browser_context_args,
        "permissions": ["clipboard-read", "clipboard-write"],
        "viewport": {"width": 1600, "height": 1000},
    }


@pytest.fixture
def evidence() -> EvidenceLog:
    return EvidenceLog()


@pytest.fixture(autouse=True)
def _require_ground_truth(request, evidence):
    """A test may assert on the site's claims, but may not pass on them alone."""
    yield
    if not request.node.get_closest_marker("live"):
        return  # unit tests assert directly; only live journeys carry evidence
    if request.node.get_closest_marker("claim_only"):
        return
    # The ledger is printed whether the test passed or failed. A failing run is
    # the one where knowing which claims held and which did not matters most,
    # and printing it only on success meant every failure arrived with the
    # evidence discarded.
    print(f"\n[evidence] {request.node.name}\n{evidence.summary()}")

    # Do not pile a second error on top of a real one. A setup error leaves no
    # rep_call at all, so both phases have to be checked or the true traceback
    # gets buried under "passed without observing anything".
    for phase in ("rep_setup", "rep_call"):
        report = getattr(request.node, phase, None)
        if report is not None and not report.passed:
            return
    # Claims are recorded rather than raised as they happen, so that a test
    # always gets as far as observing reality. They still have to hold: a
    # status box that never said what it should is a real finding, it is just
    # not a reason to stop watching the board.
    assert not evidence.failures, (
        f"{request.node.name} recorded evidence that did not hold:\n"
        + "\n".join(f"  [{e.kind.value}] {e.description}\n    {e.detail}" for e in evidence.failures)
    )
    assert evidence.has_ground_truth, (
        f"{request.node.name} passed without observing anything outside the web application.\n"
        f"Add a ground-truth assertion, or mark the test "
        f"@pytest.mark.claim_only('why no ground truth is possible').\n"
        f"{evidence.summary()}"
    )


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    setattr(item, f"rep_{call.when}", outcome.get_result())
