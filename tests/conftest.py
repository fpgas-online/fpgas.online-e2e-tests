"""Session-wide fixtures: CLI options, the browser, and evidence enforcement."""

from __future__ import annotations

import os
import random

import pytest

from e2e.evidence import EvidenceLog
from e2e.picker import OnDead
from e2e.site import Site

# The board pages autoplay a muted <video>. Chrome's autoplay policy blocks it
# anyway under automation, leaving readyState 0 with no error -- which looks
# exactly like a codec failure but is not. Measured 2026-09-12: with this flag
# both Playwright's bundled chromium (151.0.7922.34) and Google Chrome decode
# the production H.264/MPEG-TS feed to 1280x1080, readyState 4.
BROWSER_ARGS = ["--autoplay-policy=no-user-gesture-required"]


def pytest_addoption(parser):
    parser.addoption("--site", default="welland", help="welland or ps1")
    parser.addoption("--seed", type=int, default=None, help="replay a previous run's board choice")
    parser.addoption("--on-dead", default="fail", choices=[m.value for m in OnDead])


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
    # Do not pile a second error on top of a real one. A setup error leaves no
    # rep_call at all, so both phases have to be checked or the true traceback
    # gets buried under "passed without observing anything".
    for phase in ("rep_setup", "rep_call"):
        report = getattr(request.node, phase, None)
        if report is not None and not report.passed:
            return
    print(f"\n[evidence] {request.node.name}\n{evidence.summary()}")
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
