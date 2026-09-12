"""Session-wide fixtures: CLI options, the browser, and evidence enforcement."""

from __future__ import annotations

import os
import random
import shutil

import pytest

from e2e.evidence import EvidenceLog
from e2e.picker import OnDead
from e2e.site import Site

# Playwright's bundled Chromium ships without proprietary codecs, so the camera
# stream -- H.264 in MPEG-TS -- fails with MEDIA_ERR_SRC_NOT_SUPPORTED and every
# camera assertion silently sees a blank element. Use a distribution browser.
BROWSER_CANDIDATES = (
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
    "/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable",
)


def _browser_path() -> str:
    override = os.environ.get("CHROMIUM")
    if override:
        return override
    for candidate in BROWSER_CANDIDATES:
        if shutil.which(candidate):
            return candidate
    raise RuntimeError(
        "no H.264-capable browser found. Install one (apt install chromium) or set "
        f"$CHROMIUM. Looked for: {', '.join(BROWSER_CANDIDATES)}"
    )


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
    """Drive a distribution browser, never Playwright's codec-less Chromium."""
    return {**browser_type_launch_args, "executable_path": _browser_path()}


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
    report = getattr(request.node, "rep_call", None)
    if report is not None and report.failed:
        return  # the test already failed; do not pile a second error on top
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
