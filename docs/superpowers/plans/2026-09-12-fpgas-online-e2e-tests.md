# fpgas.online End-to-End Browser Tests Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `fpgas-online/fpgas.online-e2e-tests`, a public Playwright + pytest suite that uses the live fpgas.online sites the way a human does and runs against production every six hours in GitHub Actions.

**Architecture:** A small library (`e2e/`) provides the primitives -- board discovery, the web terminal, the camera, the status log, evidence accounting -- and the tests are thin journeys written against it. Everything pure is unit-tested offline against saved HTML and synthetic images, so the library is developed test-first; the three live journeys are verified by running them against production.

**Tech Stack:** Python 3.11+ with `uv`; pytest + `pytest-playwright`; Playwright driving the **system** chromium (the bundled one has no H.264); `tesseract-ocr` for OCR; Pillow + NumPy for image comparison; `paramiko` for the one direct-ssh test; `beautifulsoup4` for HTML parsing; `ruff` for lint.

**Spec:** `docs/specs/2026-09-12-fpgas-online-e2e-tests-design.md` in this repository. Its "Background: what the UI actually is", "The evidence model" and "Roadmap" sections are normative; this plan does not repeat them in full.

## Global Constraints

- **Python via `uv` only.** `uv run pytest`, `uv add`, `uv run ruff`. Never bare `python`/`pip`.
- **Dates are ISO 8601 or day-first.** Never month-first.
- **Licence: Apache 2.0.** `LICENSE` at the repo root, matching the other org repos.
- **Small, discrete commits.** One per task step group, as the tasks specify.
- **Never force push.** `main` is protected.
- **No secrets, ever.** Every credential the suite uses is one the site hands to any visitor. Nothing goes in GitHub Actions secrets.
- **No temporary files in `/tmp`.** Use a project-local `tmp/` directory, gitignored, and clean up.
- **Browser is the system chromium**, located via `$CHROMIUM` (default `/usr/bin/chromium`). Never Playwright's bundled Chromium: it has no H.264 and reports `MEDIA_ERR_SRC_NOT_SUPPORTED` on the camera stream.
- **The suite never calls** `/snmp/toggle_all` or `/snmp/off_all`.
- **OCR runs at the site's default rendering.** Never pass WebSSH's `fontsize`, `fontcolor` or `bgcolor` URL options to make text easier to read.
- **Camera assertions use element screenshots**, not frames drawn from the decoder. Direct frame reads need a comment saying why a screenshot could not answer the question.

---

## Executor notes

Read these before Task 1.

**Directories.** All the organisation's repositories are checked out side by
side under `/home/tim/github/fpgas-online/`. The new repository goes at
`/home/tim/github/fpgas-online/fpgas.online-e2e-tests`, referred to below as
`$E2E`. Work on `main` until Task 1 pushes it, then on branches.

**The two sites do not run the same code.** `welland.fpgas.online` serves
current `fpgas.online-site` main; `ps1.fpgas.online` serves the pre-split
monorepo build. The suite fails loudly on any difference. Do not add
skip-on-ps1 logic.

**Three production faults are known and expected.** Do not "fix" the tests to
go green:

1. `welland.fpgas.online:21622` and the other per-board ssh forward ports are
   unreachable from the internet. Task 11's test fails on welland.
2. `POST /pibup/upload` returns HTTP 500 on both sites: `pibup/views.py` reads
   `form.cleaned_data['run']` but `pibup/forms.py` no longer defines a `run`
   field. Task 10's test fails at the success-page step on both sites.
3. `/fpgas/tt.html` returns 404 on both sites (the view hardcodes port 21).
   Not covered until Phase 3.

**Local prerequisites.** `sudo apt install chromium tesseract-ocr
tesseract-ocr-eng fonts-dejavu-core`. Verify before Task 4 with
`tesseract --version` and `$CHROMIUM --version`.

**Never power-cycle more than one board per run**, and never during
development without need. Prefer `-k` selection to running the whole suite
while iterating.

---

## File structure

| File | Responsibility |
|---|---|
| `pyproject.toml` | package metadata, deps, pytest config |
| `ruff.toml` | lint config, line-length 120, rules E/F/W/I (matches the org) |
| `e2e/evidence.py` | `EvidenceLog`, claim vs ground truth, the enforcing fixture |
| `e2e/board.py` | `Board` dataclass, kind derivation |
| `e2e/site.py` | `Site`, `parse_boards()` over the `/fpgas/` HTML |
| `e2e/ocr.py` | tesseract wrapper, OCR-tolerant text normalisation |
| `e2e/camera.py` | video-element screenshots, liveness via the burned-in clock, diffing |
| `e2e/terminal.py` | `WebTerminal`: keystroke input, three-way output read |
| `e2e/statuslog.py` | `StatusLog`: the rendered textarea; claims only |
| `e2e/picker.py` | seeded random board choice, `--on-dead` modes |
| `tests/conftest.py` | CLI options, browser/context/page fixtures, site fixture |
| `tests/unit/` | offline tests for everything pure |
| `tests/shared/` | the three live journeys |
| `tests/tinytapeout/` | Phase 3, created empty with a README |
| `fixtures/counter_test/top.bit` | the Arty bitstream Task 10 uploads |
| `fixtures/html/` | saved `/fpgas/` pages from both sites, for unit tests |
| `.github/workflows/lint.yml` | ruff on every push |
| `.github/workflows/e2e.yml` | the six-hourly production run |
| `docs/ROADMAP.md` | the audit and phase plan |

---

## Task 1: Repository scaffold, licence, lint CI

**Files:**
- Create: `$E2E/pyproject.toml`, `$E2E/ruff.toml`, `$E2E/LICENSE`, `$E2E/README.md`, `$E2E/.gitignore`, `$E2E/e2e/__init__.py`, `$E2E/tests/__init__.py`, `$E2E/.github/workflows/lint.yml`

**Interfaces:**
- Consumes: nothing.
- Produces: the `e2e` package importable as `import e2e`; `uv run pytest` and `uv run ruff check .` both runnable.

- [ ] **Step 1: Create the repository directory and git repo**

```bash
mkdir -p /home/tim/github/fpgas-online/fpgas.online-e2e-tests
cd /home/tim/github/fpgas-online/fpgas.online-e2e-tests
git init -b main
mkdir -p e2e tests/unit tests/shared tests/tinytapeout fixtures/html .github/workflows docs tmp
```

- [ ] **Step 2: Write `pyproject.toml`**

```toml
[project]
name = "fpgas-online-e2e-tests"
version = "0.1.0"
description = "End-to-end browser tests for the fpgas.online sites"
readme = "README.md"
requires-python = ">=3.11"
license = { text = "Apache-2.0" }
dependencies = [
    "pytest>=8.0",
    "pytest-playwright>=0.5",
    "playwright>=1.47",
    "beautifulsoup4>=4.12",
    "pillow>=10.0",
    "numpy>=1.26",
    "paramiko>=3.4",
]

[dependency-groups]
dev = ["ruff>=0.6"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["e2e"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-ra --strict-markers"
markers = [
    "claim_only(reason): this control cannot be verified by ground truth; say why",
    "live: talks to a production site",
]
```

- [ ] **Step 3: Write `ruff.toml`, `.gitignore` and `LICENSE`**

`ruff.toml` (matches `fpgas.online-site`):

```toml
line-length = 120

[lint]
select = ["E", "F", "W", "I"]
```

`.gitignore`:

```
__pycache__/
*.pyc
.venv/
.pytest_cache/
test-results/
tmp/
```

`LICENSE`: copy the Apache 2.0 text from a sibling repo.

```bash
cp /home/tim/github/fpgas-online/fpgas.online-site/LICENSE LICENSE
```

- [ ] **Step 4: Write `README.md`**

```markdown
# fpgas.online-e2e-tests

End-to-end browser tests for the [fpgas.online](https://fpgas.online) sites.

The suite uses the live sites the way a person does: it opens the board pages
in a real browser, clicks the buttons, types into the web terminal the site
provides, watches the camera, and uploads bitstreams through the site's own
form. It needs no secrets -- every credential it uses is one the site hands
to any visitor.

## Running

Requires `chromium` and `tesseract-ocr` from your distribution:

    sudo apt install chromium tesseract-ocr tesseract-ocr-eng fonts-dejavu-core

Then:

    uv run pytest tests/unit                       # offline, no site contact
    uv run pytest tests/shared --site welland      # against production
    uv run pytest tests/shared --site ps1
    uv run pytest tests/shared --site welland --seed 1234 --on-dead retry
    uv run pytest tests/shared --site welland -k power_cycle --headed

`--site` takes `welland` or `ps1`. Each run prints the random seed it used, so
a failure can be replayed against the same board with `--seed`.

## What it tests

See [docs/ROADMAP.md](docs/ROADMAP.md).

These tests run against the **live production** service. They have real,
user-visible side effects: a board gets power-cycled, an FPGA gets
reprogrammed. One board is picked at random per run.

## Licence

Apache 2.0
```

- [ ] **Step 5: Create the package files**

`e2e/__init__.py` and `tests/__init__.py` are empty files.

```bash
touch e2e/__init__.py tests/__init__.py tests/unit/__init__.py
```

- [ ] **Step 6: Verify the toolchain works**

Run: `uv run ruff check . && uv run pytest tests/unit`
Expected: ruff clean; pytest exits 5 (no tests collected) -- that is fine at this point.

- [ ] **Step 7: Write `.github/workflows/lint.yml`**

```yaml
name: lint
on:
  push:
  pull_request:

jobs:
  ruff:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv run ruff check .
```

- [ ] **Step 8: Commit and create the GitHub repository**

```bash
git add -A
git commit -m "Initial scaffold: package metadata, licence, lint CI"
gh repo create fpgas-online/fpgas.online-e2e-tests --public \
  --description "End-to-end browser tests for the fpgas.online sites" \
  --source . --remote origin --push
```

- [ ] **Step 9: Apply the standard repository settings**

Per `~/.claude/GitHub.md`. Tag format is `vXX.ZZZ` (the default).

```bash
REPO="fpgas-online/fpgas.online-e2e-tests"
git tag v0.0 $(git rev-list --max-parents=0 HEAD)
git push origin v0.0
gh repo edit $REPO --enable-wiki=false --enable-projects=false
REPO_ID=$(gh api graphql -f query="query { repository(owner: \"${REPO%/*}\", name: \"${REPO#*/}\") { id } }" --jq '.data.repository.id')
gh api graphql -f query="mutation { updateRepository(input: { repositoryId: \"$REPO_ID\", hasDiscussionsEnabled: false }) { repository { hasDiscussionsEnabled } } }"
gh repo edit $REPO --enable-squash-merge=false --enable-rebase-merge=false --enable-merge-commit=true
gh repo edit $REPO --delete-branch-on-merge=true
gh api repos/$REPO -X PATCH -f security_and_analysis[secret_scanning][status]=enabled
gh api repos/$REPO -X PATCH -f security_and_analysis[secret_scanning_push_protection][status]=enabled
gh api repos/$REPO -X PATCH -f allow_update_branch=true
gh api repos/$REPO/branches/main/protection -X PUT --input - <<'EOF'
{
  "required_status_checks": null,
  "enforce_admins": false,
  "required_pull_request_reviews": null,
  "restrictions": null,
  "allow_force_pushes": false,
  "allow_deletions": false
}
EOF
uv run python ~/.claude/scripts/setup_tag_ruleset.py --owner ${REPO%/*} --repo ${REPO#*/}
```

- [ ] **Step 10: Verify the settings applied**

Run: `gh repo view $REPO --json hasWikiEnabled,hasProjectsEnabled,hasDiscussionsEnabled,deleteBranchOnMerge,squashMergeAllowed,mergeCommitAllowed,rebaseMergeAllowed`
Expected: wiki/projects/discussions false, deleteBranchOnMerge true, squash and rebase false, merge commit true.

Note: "Include Git LFS objects in archives" is UI-only. Set it by hand at
`https://github.com/$REPO/settings`.

---

## Task 2: Evidence accounting

The rule that makes this suite different from a click-through script: a test
may assert on what the site says about itself, but may never *pass* on that
alone.

**Files:**
- Create: `$E2E/e2e/evidence.py`
- Test: `$E2E/tests/unit/test_evidence.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `EvidenceLog` with `.claim(description, condition, detail="")`,
    `.ground_truth(description, condition, detail="")`, `.entries`,
    `.has_ground_truth` (bool), `.summary()` (str).
  - `EvidenceError(AssertionError)`.
  - The `evidence` pytest fixture and the autouse `_require_ground_truth`
    fixture, both registered in `tests/conftest.py` in Task 8.

- [ ] **Step 1: Write the failing test**

`tests/unit/test_evidence.py`:

```python
import pytest

from e2e.evidence import EvidenceKind, EvidenceLog


def test_a_true_claim_is_recorded_as_a_claim():
    log = EvidenceLog()
    log.claim("status box says power off", True)
    assert [e.kind for e in log.entries] == [EvidenceKind.CLAIM]
    assert log.has_ground_truth is False


def test_a_true_ground_truth_is_recorded_and_satisfies_the_requirement():
    log = EvidenceLog()
    log.ground_truth("uptime went backwards", True, detail="U0=812 U1=41")
    assert log.has_ground_truth is True


def test_a_false_claim_raises_with_the_description_and_detail():
    log = EvidenceLog()
    with pytest.raises(AssertionError) as excinfo:
        log.claim("status box says power off", False, detail="box was empty")
    assert "status box says power off" in str(excinfo.value)
    assert "box was empty" in str(excinfo.value)


def test_a_false_ground_truth_raises():
    log = EvidenceLog()
    with pytest.raises(AssertionError):
        log.ground_truth("uptime went backwards", False)


def test_a_failed_assertion_is_still_recorded_so_the_summary_shows_it():
    log = EvidenceLog()
    with pytest.raises(AssertionError):
        log.claim("nope", False)
    assert len(log.entries) == 1
    assert log.entries[0].passed is False


def test_summary_lists_every_entry_with_its_kind():
    log = EvidenceLog()
    log.claim("a claim", True)
    log.ground_truth("a fact", True)
    summary = log.summary()
    assert "[claim] a claim" in summary
    assert "[ground truth] a fact" in summary
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/unit/test_evidence.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'e2e.evidence'`

- [ ] **Step 3: Write the implementation**

`e2e/evidence.py`:

```python
"""Claim vs ground truth accounting.

A *claim* is something the web application says about itself: a line in the
status log box, a success page, a green pill. A claim may be asserted on,
because "does the status box work" is itself a feature under test. A claim may
never be the only thing a test passes on, because a claim can lie.

*Ground truth* is something observed outside the web application: the camera
picture, the Pi's own uptime, a file that really exists on the Pi, an ssh
server that really answers.

Tests record both through an EvidenceLog. A test that finishes without any
ground truth fails, unless it is explicitly marked claim_only with a reason.
"""

from __future__ import annotations

import dataclasses
import enum


class EvidenceKind(enum.Enum):
    CLAIM = "claim"
    GROUND_TRUTH = "ground truth"


@dataclasses.dataclass(frozen=True)
class Evidence:
    kind: EvidenceKind
    description: str
    detail: str
    passed: bool


class EvidenceLog:
    """Records every assertion a test makes, tagged by what kind it is."""

    def __init__(self) -> None:
        self.entries: list[Evidence] = []

    def claim(self, description: str, condition: object, detail: str = "") -> None:
        """Assert something the site says about itself."""
        self._record(EvidenceKind.CLAIM, description, condition, detail)

    def ground_truth(self, description: str, condition: object, detail: str = "") -> None:
        """Assert something observed outside the web application."""
        self._record(EvidenceKind.GROUND_TRUTH, description, condition, detail)

    def _record(self, kind: EvidenceKind, description: str, condition: object, detail: str) -> None:
        passed = bool(condition)
        self.entries.append(Evidence(kind, description, detail, passed))
        if not passed:
            message = f"[{kind.value}] {description}"
            if detail:
                message = f"{message}\n  {detail}"
            raise AssertionError(message)

    @property
    def has_ground_truth(self) -> bool:
        return any(e.kind is EvidenceKind.GROUND_TRUTH and e.passed for e in self.entries)

    def summary(self) -> str:
        lines = []
        for e in self.entries:
            mark = "ok" if e.passed else "FAILED"
            line = f"  {mark:>6}  [{e.kind.value}] {e.description}"
            if e.detail:
                line = f"{line}\n            {e.detail}"
            lines.append(line)
        return "\n".join(lines) if lines else "  (no evidence recorded)"
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/unit/test_evidence.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add e2e/evidence.py tests/unit/test_evidence.py
git commit -m "Evidence accounting: claims may be asserted, never passed on alone"
```

---

## Task 3: Board discovery from the index page

**Files:**
- Create: `$E2E/e2e/board.py`, `$E2E/e2e/site.py`
- Create: `$E2E/fixtures/html/welland-fpgas-index.html`, `$E2E/fixtures/html/ps1-fpgas-index.html`
- Test: `$E2E/tests/unit/test_site.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `Board(hostname: str, port: int, fpga_board: str)` with `.kind` -> `"arty" | "acorn" | "tt" | "unknown"` and `.page_path` -> e.g. `"/fpgas/pi16.html"`.
  - `Site(name: str, base_url: str)` with `.index_url` and `.classmethod from_name(name)`.
  - `parse_boards(html: str) -> list[Board]`.

- [ ] **Step 1: Save the two index pages as fixtures**

These are inputs to the parser tests, so they must be real.

```bash
curl -sS -m 30 https://welland.fpgas.online/fpgas/ -o fixtures/html/welland-fpgas-index.html
curl -sS -m 30 https://ps1.fpgas.online/fpgas/ -o fixtures/html/ps1-fpgas-index.html
```

Verify both are non-empty and contain board cards:

Run: `grep -c 'Use this FPGA' fixtures/html/*.html`
Expected: welland 14, ps1 9.

- [ ] **Step 2: Write the failing test**

`tests/unit/test_site.py`:

```python
from pathlib import Path

import pytest

from e2e.site import Site, parse_boards

FIXTURES = Path(__file__).parents[2] / "fixtures" / "html"


@pytest.fixture
def welland_boards():
    return parse_boards((FIXTURES / "welland-fpgas-index.html").read_text())


@pytest.fixture
def ps1_boards():
    return parse_boards((FIXTURES / "ps1-fpgas-index.html").read_text())


def test_welland_index_lists_fourteen_boards(welland_boards):
    assert len(welland_boards) == 14


def test_welland_board_carries_hostname_port_and_fpga(welland_boards):
    first = welland_boards[0]
    assert first.hostname == "pi-sw2-p16"
    assert first.port == 16
    assert first.fpga_board == "Digilent Arty A7-35T"


def test_ps1_index_lists_nine_boards_with_the_older_heading_format(ps1_boards):
    assert len(ps1_boards) == 9
    assert ps1_boards[0].hostname == "pi2"
    assert ps1_boards[0].port == 2


def test_board_kind_is_derived_from_the_fpga_name(welland_boards):
    kinds = {b.hostname: b.kind for b in welland_boards}
    assert kinds["pi-sw2-p16"] == "arty"
    assert kinds["pi-sw2-p29"] == "acorn"
    assert kinds["pi-sw2-p33"] == "tt"


def test_a_board_with_no_fpga_named_is_unknown_kind(ps1_boards):
    assert ps1_boards[0].kind == "unknown"


def test_page_path_uses_the_port_not_the_hostname(welland_boards):
    assert welland_boards[0].page_path == "/fpgas/pi16.html"


def test_site_from_name_builds_the_base_url():
    assert Site.from_name("welland").base_url == "https://welland.fpgas.online"
    assert Site.from_name("ps1").index_url == "https://ps1.fpgas.online/fpgas/"


def test_site_from_name_rejects_an_unknown_site():
    with pytest.raises(ValueError):
        Site.from_name("nowhere")
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `uv run pytest tests/unit/test_site.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'e2e.site'`

- [ ] **Step 4: Write `e2e/board.py`**

```python
"""One FPGA board as the index page presents it."""

from __future__ import annotations

import dataclasses

# Longest / most specific first: "TT FPGA emulation (iCE40UP5K)" must not be
# mistaken for anything else, and an Acorn is never an Arty.
_KINDS = (
    ("arty", ("arty",)),
    ("acorn", ("acorn",)),
    ("tt", ("tt fpga", "tiny tapeout", "tinytapeout")),
)


@dataclasses.dataclass(frozen=True)
class Board:
    hostname: str
    port: int
    fpga_board: str

    @property
    def kind(self) -> str:
        """arty | acorn | tt | unknown, derived from the board name shown to users."""
        haystack = self.fpga_board.lower()
        for kind, needles in _KINDS:
            if any(n in haystack for n in needles):
                return kind
        return "unknown"

    @property
    def page_path(self) -> str:
        """The per-board page, which is addressed by switch port, not hostname."""
        return f"/fpgas/pi{self.port}.html"
```

- [ ] **Step 5: Write `e2e/site.py`**

```python
"""A deployment of the /fpgas/ application, and the boards it lists."""

from __future__ import annotations

import dataclasses
import re

from bs4 import BeautifulSoup

from e2e.board import Board

SITES = {
    "welland": "https://welland.fpgas.online",
    "ps1": "https://ps1.fpgas.online",
}

# welland: "pi-sw2-p16"   ps1: "FPGA pi2"
_HOSTNAME_PREFIX = re.compile(r"^\s*FPGA\s+", re.IGNORECASE)
_PAGE_HREF = re.compile(r"^pi(\d+)\.html$")


@dataclasses.dataclass(frozen=True)
class Site:
    name: str
    base_url: str

    @classmethod
    def from_name(cls, name: str) -> "Site":
        try:
            return cls(name, SITES[name])
        except KeyError:
            raise ValueError(f"unknown site {name!r}; known: {', '.join(sorted(SITES))}") from None

    @property
    def index_url(self) -> str:
        return f"{self.base_url}/fpgas/"

    def url(self, path: str) -> str:
        return f"{self.base_url}{path}"


def parse_boards(html: str) -> list[Board]:
    """Read the board cards off a rendered /fpgas/ page.

    Each card is a table whose first cell holds an <h1> with the board name and
    (on current deployments) the FPGA name as trailing text, and whose second
    cell links to piNN.html. PS1 runs an older build whose heading reads
    "FPGA pi2" and which names no FPGA at all.
    """
    soup = BeautifulSoup(html, "html.parser")
    boards: list[Board] = []
    for link in soup.find_all("a", href=_PAGE_HREF):
        card = link.find_parent("table")
        if card is None:
            continue
        heading = card.find("h1")
        if heading is None:
            continue
        hostname = _HOSTNAME_PREFIX.sub("", heading.get_text()).strip()
        port = int(_PAGE_HREF.match(link["href"]).group(1))
        fpga = "".join(s for s in heading.next_siblings if isinstance(s, str)).strip()
        boards.append(Board(hostname=hostname, port=port, fpga_board=fpga))
    return boards
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `uv run pytest tests/unit/test_site.py -v`
Expected: 8 passed

- [ ] **Step 7: Commit**

```bash
git add e2e/board.py e2e/site.py tests/unit/test_site.py fixtures/html/
git commit -m "Discover boards from the index page both deployments render"
```

---

## Task 4: OCR wrapper

**Files:**
- Create: `$E2E/e2e/ocr.py`
- Test: `$E2E/tests/unit/test_ocr.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `read_text(image: PIL.Image.Image, *, psm: int = 6, whitelist: str | None = None) -> str`
  - `read_clock(image) -> str | None` -- returns `HH:MM:SS` or None.
  - `strip_ansi(text: str) -> str`
  - `normalise(text: str) -> str` -- strip escapes, collapse whitespace, for comparison.
  - `looks_like(a: str, b: str, threshold: float = 0.85) -> bool`
  - `OcrUnavailable(RuntimeError)`

- [ ] **Step 1: Write the failing test**

`tests/unit/test_ocr.py`:

```python
from PIL import Image, ImageDraw, ImageFont

from e2e import ocr


def _render(text: str, size=(420, 60), fontsize=32) -> Image.Image:
    """White-on-black monospace, like a terminal or the camera's clock overlay."""
    img = Image.new("RGB", size, "black")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", fontsize)
    except OSError:
        font = ImageFont.load_default()
    draw.text((6, 6), text, fill="white", font=font)
    return img


def test_read_text_reads_a_rendered_line():
    assert "hello world" in ocr.read_text(_render("hello world")).lower()


def test_read_clock_reads_a_timestamp():
    assert ocr.read_clock(_render("12:34:56")) == "12:34:56"


def test_read_clock_returns_none_when_there_is_no_clock():
    assert ocr.read_clock(_render("no clock here")) is None


def test_normalise_collapses_whitespace_and_strips():
    assert ocr.normalise("  a \t b\n\n c  ") == "a b c"


def test_normalise_removes_ansi_escape_sequences():
    assert ocr.normalise("\x1b[32mgreen\x1b[0m text") == "green text"


def test_looks_like_tolerates_a_few_ocr_errors():
    assert ocr.looks_like("total 2192119 top.bit", "total 2l92ll9 top.bit")


def test_looks_like_rejects_different_text():
    assert not ocr.looks_like("permission denied", "total 2192119 top.bit")
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/unit/test_ocr.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'e2e.ocr'`

- [ ] **Step 3: Write the implementation**

`e2e/ocr.py`:

```python
"""Reading text out of pictures, and comparing text that came from a picture.

OCR is how the suite checks that what the *user* sees matches what the server
sent. It deliberately runs against the site's default rendering: if tesseract
cannot read the terminal at the size and contrast the site ships, a human is
probably struggling too, and that is a finding rather than something to work
around by passing WebSSH its font options.
"""

from __future__ import annotations

import difflib
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image

CLOCK_WHITELIST = "0123456789:"
_CLOCK = re.compile(r"\b([0-2]?\d:[0-5]\d:[0-5]\d)\b")
_ANSI = re.compile(
    r"\x1b\[[0-9;?]*[ -/]*[@-~]"      # CSI sequences
    r"|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)"  # OSC sequences
    r"|\x1b[()][B0]"                   # charset selection
    r"|\x1b[=>]"                       # keypad mode
)
_WHITESPACE = re.compile(r"\s+")


class OcrUnavailable(RuntimeError):
    pass


def read_text(image: Image.Image, *, psm: int = 6, whitelist: str | None = None) -> str:
    """Run tesseract over an image and return what it read."""
    if shutil.which("tesseract") is None:
        raise OcrUnavailable("tesseract is not installed; apt install tesseract-ocr tesseract-ocr-eng")
    with tempfile.TemporaryDirectory(dir="tmp") as scratch:
        path = Path(scratch) / "ocr.png"
        image.save(path)
        cmd = ["tesseract", str(path), "-", "--psm", str(psm)]
        if whitelist:
            cmd += ["-c", f"tessedit_char_whitelist={whitelist}"]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise OcrUnavailable(f"tesseract failed ({proc.returncode}): {proc.stderr.strip()}")
    return proc.stdout


def read_clock(image: Image.Image) -> str | None:
    """Read an HH:MM:SS clock, such as the one the Pi burns into the camera picture."""
    match = _CLOCK.search(read_text(image, psm=7, whitelist=CLOCK_WHITELIST))
    return match.group(1) if match else None


def strip_ansi(text: str) -> str:
    """Remove terminal escape sequences, keeping the characters a user sees."""
    return _ANSI.sub("", text)


def normalise(text: str) -> str:
    """Strip terminal escapes and collapse whitespace, so two readings can be compared."""
    return _WHITESPACE.sub(" ", strip_ansi(text)).strip()


def looks_like(a: str, b: str, threshold: float = 0.85) -> bool:
    """True when two strings are the same modulo a few OCR misreadings."""
    return difflib.SequenceMatcher(None, normalise(a), normalise(b)).ratio() >= threshold
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/unit/test_ocr.py -v`
Expected: 7 passed

If `read_text` fails with `OcrUnavailable`, install tesseract as the Executor
notes say. Do not stub it out: a missing OCR engine must be loud.

- [ ] **Step 5: Commit**

```bash
git add e2e/ocr.py tests/unit/test_ocr.py
git commit -m "OCR wrapper: read the screen, compare readings tolerantly"
```

---

## Task 5: Camera

**Files:**
- Create: `$E2E/e2e/camera.py`
- Test: `$E2E/tests/unit/test_camera.py`

**Interfaces:**
- Consumes: `e2e.ocr.read_clock`, `e2e.ocr` normalisation.
- Produces:
  - `difference(a: Image.Image, b: Image.Image, region: tuple | None = None) -> float` -- 0.0 identical, 1.0 maximally different.
  - `crop_fraction(image, left, top, width, height) -> Image.Image` -- fractions of the image size.
  - `Camera(page, video_selector)` with `.shot() -> Image.Image`, `.clock() -> str | None`, `.is_live(samples=2, gap=3.0) -> tuple[bool, str]`, `.wait_until_live(timeout)`, `.wait_until_not_live(timeout)`.

- [ ] **Step 1: Write the failing test**

`tests/unit/test_camera.py`:

```python
from PIL import Image, ImageDraw

from e2e import camera


def _solid(colour, size=(320, 200)):
    return Image.new("RGB", size, colour)


def _with_led(colour, size=(320, 200)):
    img = Image.new("RGB", size, "black")
    ImageDraw.Draw(img).rectangle([10, 170, 120, 195], fill=colour)
    return img


def test_identical_images_have_zero_difference():
    assert camera.difference(_solid("black"), _solid("black")) == 0.0


def test_black_and_white_are_maximally_different():
    assert camera.difference(_solid("black"), _solid("white")) > 0.99


def test_a_small_change_is_a_small_whole_image_difference():
    assert 0.0 < camera.difference(_with_led("black"), _with_led("red")) < 0.2


def test_restricting_to_the_led_region_amplifies_that_same_change():
    led = (0.0, 0.8, 0.45, 0.2)
    whole = camera.difference(_with_led("black"), _with_led("red"))
    region = camera.difference(_with_led("black"), _with_led("red"), region=led)
    assert region > whole * 3


def test_crop_fraction_takes_fractions_of_the_image():
    cropped = camera.crop_fraction(_solid("black", (400, 200)), 0.0, 0.0, 0.5, 0.25)
    assert cropped.size == (200, 50)


def test_images_of_different_sizes_are_compared_after_resizing():
    assert camera.difference(_solid("black", (320, 200)), _solid("black", (640, 400))) == 0.0
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/unit/test_camera.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'e2e.camera'`

- [ ] **Step 3: Write the implementation**

`e2e/camera.py`:

```python
"""What the camera shows, as the page renders it.

Assertions use screenshots of the <video> element rather than frames drawn out
of the decoder, because a screenshot is what the user sees. The Pi burns a
clock into the picture, so "is this feed live?" is answered by OCRing that
clock twice and checking it advanced -- which a frozen picture cannot fake.

Because the camera runs on the Pi (fpgas-online-cam's cam.service), the feed
going away is itself evidence that the Pi lost power.
"""

from __future__ import annotations

import io
import time

import numpy as np
from PIL import Image

from e2e import ocr

# The Pi draws its clock in the top-left corner; the same fractions
# fpgas.online-cam/tests/measure-latency.mjs uses.
CLOCK_REGION = (0.0, 0.0, 0.30, 0.12)


def crop_fraction(image: Image.Image, left: float, top: float, width: float, height: float) -> Image.Image:
    w, h = image.size
    box = (round(left * w), round(top * h), round((left + width) * w), round((top + height) * h))
    return image.crop(box)


def difference(a: Image.Image, b: Image.Image, region: tuple | None = None) -> float:
    """Mean absolute per-channel difference, normalised to 0.0 - 1.0."""
    if region is not None:
        a, b = crop_fraction(a, *region), crop_fraction(b, *region)
    if a.size != b.size:
        b = b.resize(a.size)
    left = np.asarray(a.convert("RGB"), dtype=np.int16)
    right = np.asarray(b.convert("RGB"), dtype=np.int16)
    return float(np.abs(left - right).mean() / 255.0)


class Camera:
    """The video element on a board page."""

    def __init__(self, page, video_selector: str):
        self.page = page
        self.selector = video_selector

    def shot(self) -> Image.Image:
        """A screenshot of the video element as rendered."""
        return Image.open(io.BytesIO(self.page.locator(self.selector).screenshot()))

    def clock(self) -> str | None:
        """The clock the Pi burns into the picture, or None if it cannot be read."""
        return ocr.read_clock(crop_fraction(self.shot(), *CLOCK_REGION))

    def is_live(self, gap: float = 3.0) -> tuple[bool, str]:
        """True when the burned-in clock advanced across two readings `gap` seconds apart."""
        first = self.clock()
        time.sleep(gap)
        second = self.clock()
        detail = f"clock {first!r} -> {second!r}"
        return (first is not None and second is not None and first != second), detail

    def wait_until_live(self, timeout: float, gap: float = 3.0) -> str:
        """Block until the feed is live. Returns the detail string; raises on timeout."""
        return self._wait(True, timeout, gap)

    def wait_until_not_live(self, timeout: float, gap: float = 3.0) -> str:
        """Block until the feed stops advancing -- i.e. the Pi stopped sending."""
        return self._wait(False, timeout, gap)

    def _wait(self, want_live: bool, timeout: float, gap: float) -> str:
        deadline = time.monotonic() + timeout
        detail = "never sampled"
        while time.monotonic() < deadline:
            try:
                live, detail = self.is_live(gap=gap)
            except Exception as exc:  # noqa: BLE001 - a dead player raises in many ways
                live, detail = False, f"could not read the picture: {exc}"
            if live == want_live:
                return detail
        state = "live" if want_live else "not live"
        raise TimeoutError(f"camera did not become {state} within {timeout}s ({detail})")
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/unit/test_camera.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add e2e/camera.py tests/unit/test_camera.py
git commit -m "Camera: screenshots, LED-region diffing, liveness from the burned-in clock"
```

---

## Task 6: The web terminal

The suite's primary channel for shell work. Input is real keystrokes; output
is read three independent ways and required to agree, because the terminal is
a canvas and none of the three is trustworthy alone.

**Files:**
- Create: `$E2E/e2e/terminal.py`
- Test: `$E2E/tests/unit/test_terminal.py`

**Interfaces:**
- Consumes: `e2e.ocr`.
- Produces:
  - `decode_wssh_frames(frames: list[str]) -> str` -- concatenate the `{"data": ...}` payloads.
  - `strip_prompt_and_echo(text: str, command: str, prompt: str) -> str`
  - `TerminalOutput(websocket: str, clipboard: str, ocr_text: str)` with `.text`, `.shows(needle) -> tuple[bool, str]`.
  - `WebTerminal(page, frame_selector="#wssh_if")` with `.attach()`, `.wait_for_prompt(timeout)`, `.run(cmd, timeout=30) -> TerminalOutput`, `.exit_status() -> int`, `.reset()`, `.reconnect()`.

- [ ] **Step 1: Write the failing test**

`tests/unit/test_terminal.py`:

```python
import pytest

from e2e.terminal import TerminalOutput, decode_wssh_frames, strip_prompt_and_echo


def test_decode_wssh_frames_concatenates_the_data_payloads():
    frames = ['{"data": "hel"}', '{"data": "lo\\r\\n"}']
    assert decode_wssh_frames(frames) == "hel" + "lo\r\n"


def test_decode_wssh_frames_ignores_frames_without_data():
    frames = ['{"status": "ok"}', '{"data": "x"}', "not json at all"]
    assert decode_wssh_frames(frames) == "x"


def test_strip_prompt_and_echo_removes_the_typed_command_and_the_trailing_prompt():
    raw = "cat /proc/uptime\r\n812.34 1600.11\r\npi@pi-sw2-p16:~ $ "
    assert strip_prompt_and_echo(raw, "cat /proc/uptime", r"\$ $") == "812.34 1600.11"


def test_output_shows_a_needle_present_in_all_three_readings():
    out = TerminalOutput(
        websocket="total 2192119 top.bit",
        clipboard="total 2192119 top.bit",
        ocr_text="total 2l92ll9 top.bit",
    )
    shown, detail = out.shows("top.bit")
    assert shown, detail


def test_output_does_not_show_a_needle_missing_from_the_clipboard():
    out = TerminalOutput(
        websocket="total 2192119 top.bit",
        clipboard="",
        ocr_text="total 2192119 top.bit",
    )
    shown, detail = out.shows("top.bit")
    assert not shown
    assert "clipboard" in detail


def test_output_accepts_ocr_that_merely_resembles_the_websocket_text():
    """OCR mangles digits; the needle must still be recognisable, not exact."""
    out = TerminalOutput(
        websocket="Arty pmod wire test passed",
        clipboard="Arty pmod wire test passed",
        ocr_text="Arty pmod wlre test passed",
    )
    shown, detail = out.shows("wire test passed")
    assert shown, detail


def test_output_text_prefers_the_websocket_reading():
    out = TerminalOutput(websocket="a", clipboard="b", ocr_text="c")
    assert out.text == "a"


def test_ansi_sequences_do_not_hide_a_needle():
    out = TerminalOutput(
        websocket="\x1b[0;32mpi@host\x1b[0m:~ $ done",
        clipboard="pi@host:~ $ done",
        ocr_text="pi@host:~ $ done",
    )
    shown, _ = out.shows("done")
    assert shown


@pytest.mark.parametrize("needle", ["", "   "])
def test_shows_rejects_an_empty_needle(needle):
    out = TerminalOutput(websocket="x", clipboard="x", ocr_text="x")
    with pytest.raises(ValueError):
        out.shows(needle)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/unit/test_terminal.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'e2e.terminal'`

- [ ] **Step 3: Write the implementation**

`e2e/terminal.py`:

```python
"""The web terminal the board page embeds, driven the way a person drives it.

The page embeds huashengdun/webssh in an iframe whose URL already carries the
credentials, so nothing here needs a password.

WebSSH bundles xterm.js 4.x with the default canvas renderer, so the terminal
text is NOT in the DOM and the xterm buffer API is locked inside a closure.
Output is therefore read three independent ways, and an assertion must hold in
all three:

  1. the WebSSH WebSocket frames -- exact, cheap, but transport rather than
     screen, so on its own only a claim about what is displayed;
  2. the clipboard, after selecting the terminal and copying, which is the
     gesture a person uses to grab terminal output;
  3. OCR of a screenshot, which is literally what is on the screen.

Input is always real keystrokes.
"""

from __future__ import annotations

import json
import re
import time

from e2e import ocr

DEFAULT_PROMPT = r"[$#] $"
_WSSH_WS = "/wssh/ws"


def decode_wssh_frames(frames: list[str]) -> str:
    """Concatenate the terminal output carried by WebSSH's {"data": ...} frames."""
    out = []
    for frame in frames:
        try:
            payload = json.loads(frame)
        except (TypeError, ValueError):
            continue
        if isinstance(payload, dict) and isinstance(payload.get("data"), str):
            out.append(payload["data"])
    return "".join(out)


def strip_prompt_and_echo(text: str, command: str, prompt: str = DEFAULT_PROMPT) -> str:
    """Drop the echoed command and the prompt the shell printed afterwards."""
    body = ocr.strip_ansi(text)
    lines = [line.rstrip("\r") for line in body.split("\n")]
    if lines and command.strip() and command.strip() in lines[0]:
        lines = lines[1:]
    while lines and re.search(prompt, lines[-1]):
        lines = lines[:-1]
    return "\n".join(lines).strip()


class TerminalOutput:
    """One command's output as read three ways."""

    def __init__(self, websocket: str, clipboard: str, ocr_text: str):
        self.websocket = websocket
        self.clipboard = clipboard
        self.ocr_text = ocr_text

    @property
    def text(self) -> str:
        """The canonical reading. Exact, but only trustworthy once `shows` agrees."""
        return self.websocket

    def shows(self, needle: str) -> tuple[bool, str]:
        """True when `needle` is visible in all three readings.

        The websocket and clipboard must contain it after normalisation. OCR is
        allowed to have misread characters, so it passes if it contains the
        needle, or if the whole OCR reading resembles the websocket reading.
        """
        if not needle.strip():
            raise ValueError("needle must not be empty")
        wanted = ocr.normalise(needle)
        in_ws = wanted in ocr.normalise(self.websocket)
        in_clip = wanted in ocr.normalise(self.clipboard)
        in_ocr = wanted in ocr.normalise(self.ocr_text) or ocr.looks_like(self.ocr_text, self.websocket)
        missing = [
            name
            for name, present in (("websocket", in_ws), ("clipboard", in_clip), ("screen (ocr)", in_ocr))
            if not present
        ]
        detail = (
            f"{needle!r} seen in all three readings"
            if not missing
            else f"{needle!r} missing from: {', '.join(missing)}\n"
            f"  websocket: {self.websocket!r}\n"
            f"  clipboard: {self.clipboard!r}\n"
            f"  screen:    {self.ocr_text!r}"
        )
        return (not missing), detail


class WebTerminal:
    """The wssh iframe on a board page."""

    def __init__(self, page, frame_selector: str = "#wssh_if", prompt: str = DEFAULT_PROMPT):
        self.page = page
        self.frame_selector = frame_selector
        self.prompt = prompt
        self._frames: list[str] = []

    # -- lifecycle --

    def attach(self) -> None:
        """Start recording the terminal's WebSocket. Call before navigating."""

        def on_websocket(ws):
            if _WSSH_WS in ws.url:
                ws.on("framereceived", lambda payload: self._frames.append(payload))

        self.page.on("websocket", on_websocket)

    def wait_for_prompt(self, timeout: float = 60.0) -> None:
        """Block until the shell has printed a prompt."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if re.search(self.prompt, decode_wssh_frames(self._frames).rstrip()):
                return
            self.page.wait_for_timeout(500)
        raise TimeoutError(f"no shell prompt within {timeout}s; saw {decode_wssh_frames(self._frames)!r}")

    def reset(self) -> None:
        """Forget buffered output -- e.g. after navigating away and back."""
        self._frames.clear()

    def reconnect(self) -> None:
        """Click the page's own 'reset ssh' button, as a person would."""
        self._frames.clear()
        self.page.click("#wssh-connect")
        self.wait_for_prompt()

    # -- interaction --

    def _focus(self):
        frame = self.page.frame_locator(self.frame_selector)
        frame.locator(".xterm-screen").click()
        return frame

    def run(self, command: str, timeout: float = 30.0, settle: float = 1.5) -> TerminalOutput:
        """Type a command, wait for the prompt, and read the output three ways."""
        self._focus()
        mark = len(self._frames)
        self.page.keyboard.type(command)
        self.page.keyboard.press("Enter")

        deadline = time.monotonic() + timeout
        last_len, quiet_since = -1, None
        while time.monotonic() < deadline:
            raw = decode_wssh_frames(self._frames[mark:])
            if len(raw) != last_len:
                last_len, quiet_since = len(raw), None
            elif re.search(self.prompt, raw.rstrip()):
                quiet_since = quiet_since or time.monotonic()
                if time.monotonic() - quiet_since >= settle:
                    break
            self.page.wait_for_timeout(250)

        raw = decode_wssh_frames(self._frames[mark:])
        return TerminalOutput(
            websocket=strip_prompt_and_echo(raw, command, self.prompt),
            clipboard=strip_prompt_and_echo(self._copy_visible(), command, self.prompt),
            ocr_text=self._ocr_visible(),
        )

    def exit_status(self) -> int:
        """Ask the shell what the last command returned, the way the site's own demos do."""
        out = self.run("echo $?")
        match = re.search(r"-?\d+", out.text)
        if match is None:
            raise AssertionError(f"could not read an exit status from {out.text!r}")
        return int(match.group())

    # -- the two screen-side readings --

    def _copy_visible(self) -> str:
        """Select the terminal viewport and copy, the way a person grabs output."""
        frame = self.page.frame_locator(self.frame_selector)
        box = frame.locator(".xterm-screen").bounding_box()
        if box is None:
            return ""
        self.page.mouse.move(box["x"] + 2, box["y"] + 2)
        self.page.mouse.down()
        self.page.mouse.move(box["x"] + box["width"] - 2, box["y"] + box["height"] - 2, steps=8)
        self.page.mouse.up()
        self.page.keyboard.press("Control+Insert")
        return self.page.evaluate("navigator.clipboard.readText()")

    def _ocr_visible(self) -> str:
        import io

        from PIL import Image

        shot = self.page.frame_locator(self.frame_selector).locator(".xterm-screen").screenshot()
        return ocr.read_text(Image.open(io.BytesIO(shot)), psm=6)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/unit/test_terminal.py -v`
Expected: 10 passed

- [ ] **Step 5: Commit**

```bash
git add e2e/terminal.py tests/unit/test_terminal.py
git commit -m "Web terminal: keystroke input, output read three ways and required to agree"
```

---

## Task 7: Status log and board picker

**Files:**
- Create: `$E2E/e2e/statuslog.py`, `$E2E/e2e/picker.py`
- Test: `$E2E/tests/unit/test_picker.py`

**Interfaces:**
- Consumes: `e2e.board.Board`.
- Produces:
  - `StatusLog(page, port)` with `.text() -> str`, `.wait_for(needle, timeout) -> tuple[bool, str]`.
  - `choose(boards, kind, seed) -> list[Board]` -- the shuffled candidate order.
  - `OnDead` enum with `FAIL` and `RETRY`.
  - `NoSuchBoard(RuntimeError)`.

- [ ] **Step 1: Write the failing test**

`tests/unit/test_picker.py`:

```python
import pytest

from e2e.board import Board
from e2e.picker import NoSuchBoard, OnDead, choose

BOARDS = [
    Board("pi-sw2-p16", 16, "Digilent Arty A7-35T"),
    Board("pi-sw2-p29", 29, "Sqrl Acorn CLE-215+"),
    Board("pi-sw2-p37", 37, "Digilent Arty A7-35T"),
    Board("pi-sw2-p33", 33, "TT FPGA emulation (iCE40UP5K)"),
]


def test_choose_returns_only_boards_of_the_requested_kind():
    assert {b.port for b in choose(BOARDS, "arty", seed=1)} == {16, 37}


def test_choose_is_deterministic_for_a_given_seed():
    assert [b.port for b in choose(BOARDS, "arty", seed=7)] == [b.port for b in choose(BOARDS, "arty", seed=7)]


def test_choose_shuffles_so_different_seeds_can_give_different_orders():
    orders = {tuple(b.port for b in choose(BOARDS, "arty", seed=s)) for s in range(20)}
    assert len(orders) > 1


def test_choose_raises_when_no_board_of_that_kind_exists():
    with pytest.raises(NoSuchBoard):
        choose(BOARDS, "spartan", seed=1)


def test_on_dead_parses_from_the_command_line_values():
    assert OnDead("fail") is OnDead.FAIL
    assert OnDead("retry") is OnDead.RETRY
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/unit/test_picker.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'e2e.picker'`

- [ ] **Step 3: Write `e2e/picker.py`**

```python
"""Choosing which board to test on.

One board per run, picked at random, so a user is unlikely to collide with a
test and the fleet is exercised evenly. The seed is printed by the test
session so any run can be replayed against the same board.
"""

from __future__ import annotations

import enum
import random

from e2e.board import Board


class OnDead(enum.Enum):
    """What to do when the chosen board turns out not to be working."""

    FAIL = "fail"
    RETRY = "retry"


class NoSuchBoard(RuntimeError):
    pass


def choose(boards: list[Board], kind: str, seed: int) -> list[Board]:
    """Candidate boards of `kind`, in a seeded random order."""
    candidates = [b for b in boards if b.kind == kind]
    if not candidates:
        listed = ", ".join(sorted({b.kind for b in boards})) or "none"
        raise NoSuchBoard(f"the site lists no {kind!r} board; it lists: {listed}")
    random.Random(seed).shuffle(candidates)
    return candidates
```

- [ ] **Step 4: Write `e2e/statuslog.py`**

No unit test: it is a thin read of one DOM element, and every behaviour worth
asserting needs a live page. It is exercised by Tasks 9 and 10.

```python
"""The status log box on a board page.

The textarea under the video, which the page fills with the Pi's own reports
and the SNMP results. It is rendered on screen, so a test may assert on it --
but it is the site talking about itself, so it is never enough on its own.
Everything here produces claims.
"""

from __future__ import annotations

import time


class StatusLog:
    def __init__(self, page, port: int):
        self.page = page
        self.selector = f"#log{port}"

    def text(self) -> str:
        return self.page.locator(self.selector).input_value()

    def wait_for(self, needle: str, timeout: float = 60.0) -> tuple[bool, str]:
        """Wait for a line to appear. Returns (seen, detail) rather than raising."""
        deadline = time.monotonic() + timeout
        seen = ""
        while time.monotonic() < deadline:
            seen = self.text()
            if needle in seen:
                return True, f"{needle!r} appeared in the status box"
            self.page.wait_for_timeout(500)
        tail = "\n".join(seen.splitlines()[-8:])
        return False, f"{needle!r} never appeared within {timeout}s; box ended:\n{tail}"
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/unit -v`
Expected: all pass (evidence 6, site 8, ocr 7, camera 6, picker 5 = 32)

- [ ] **Step 6: Commit**

```bash
git add e2e/picker.py e2e/statuslog.py tests/unit/test_picker.py
git commit -m "Board picker and status log reader"
```

---

## Task 8: Test harness -- fixtures and CLI options

**Files:**
- Create: `$E2E/tests/conftest.py`, `$E2E/tests/shared/conftest.py`, `$E2E/tests/shared/__init__.py`

**Interfaces:**
- Consumes: everything from Tasks 2-7.
- Produces fixtures: `site`, `seed`, `on_dead`, `evidence`, `browser_type_launch_args`, `browser_context_args`, and `board_page(kind)` -- a factory returning `(board, page, terminal, camera, status)`.

- [ ] **Step 1: Write `tests/conftest.py`**

```python
"""Session-wide fixtures: CLI options, the browser, and evidence enforcement."""

from __future__ import annotations

import os
import random

import pytest

from e2e.evidence import EvidenceLog
from e2e.picker import OnDead
from e2e.site import Site

CHROMIUM = os.environ.get("CHROMIUM", "/usr/bin/chromium")


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
    """Drive the system chromium.

    Playwright's bundled Chromium ships without H.264, so the camera stream --
    H.264 in MPEG-TS -- fails with MEDIA_ERR_SRC_NOT_SUPPORTED and every camera
    assertion silently sees a blank element.
    """
    return {**browser_type_launch_args, "executable_path": CHROMIUM}


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
```

- [ ] **Step 2: Write `tests/shared/conftest.py`**

```python
"""The board_page factory: pick a board, open it, and wire up the primitives."""

from __future__ import annotations

import dataclasses

import pytest

from e2e.camera import Camera
from e2e.picker import OnDead, choose
from e2e.site import parse_boards
from e2e.statuslog import StatusLog
from e2e.terminal import WebTerminal


@dataclasses.dataclass
class BoardSession:
    board: object
    page: object
    terminal: WebTerminal
    camera: Camera
    status: StatusLog


@pytest.fixture
def board_page(page, site, seed, on_dead, evidence):
    """Factory: board_page("arty") -> BoardSession on a live, working board."""

    def _open(kind: str) -> BoardSession:
        page.goto(site.index_url, wait_until="domcontentloaded")
        boards = parse_boards(page.content())
        evidence.ground_truth(
            f"the index page lists at least one {kind} board",
            any(b.kind == kind for b in boards),
            detail=f"listed: {[(b.hostname, b.kind) for b in boards]}",
        )

        candidates = choose(boards, kind, seed)
        problems = []
        for board in candidates:
            session = _attach(board)
            ok, why = _is_working(session)
            if ok:
                print(f"[e2e] testing on {board.hostname} ({board.fpga_board})")
                return session
            problems.append(f"{board.hostname}: {why}")
            if on_dead is OnDead.FAIL:
                break
        raise AssertionError(
            "no usable board.\n  " + "\n  ".join(problems) + f"\n(--on-dead={on_dead.value})"
        )

    def _attach(board) -> BoardSession:
        terminal = WebTerminal(page)
        terminal.attach()
        page.goto(site.url(board.page_path), wait_until="domcontentloaded")
        return BoardSession(
            board=board,
            page=page,
            terminal=terminal,
            camera=Camera(page, f"#video-player{board.port}"),
            status=StatusLog(page, board.port),
        )

    def _is_working(session) -> tuple[bool, str]:
        """The glance a person gives a board before using it."""
        try:
            session.terminal.wait_for_prompt(timeout=45)
        except TimeoutError as exc:
            return False, f"the web terminal never reached a prompt ({exc})"
        try:
            live, detail = session.camera.is_live()
        except Exception as exc:  # noqa: BLE001
            return False, f"the camera could not be read ({exc})"
        return (live, "the camera feed is live" if live else f"the camera feed is not live ({detail})")

    return _open
```

- [ ] **Step 3: Verify the harness collects**

```bash
touch tests/shared/__init__.py
```

Run: `uv run pytest tests/shared --collect-only --site welland`
Expected: collects 0 tests without error (no test files yet).

- [ ] **Step 4: Commit**

```bash
git add tests/conftest.py tests/shared/conftest.py tests/shared/__init__.py
git commit -m "Test harness: system chromium, clipboard access, board selection, evidence enforcement"
```

---

## Task 9: Test 1 -- power cycling

**Files:**
- Create: `$E2E/tests/shared/test_power_cycle.py`

**Interfaces:**
- Consumes: `board_page`, `evidence`.
- Produces: nothing other tasks use.

- [ ] **Step 1: Write the test**

This is a live journey, so there is no red-then-green cycle against a fake.
It is verified by running it against production in Step 2.

```python
"""Does 'turn it off and on again' actually turn the board off and on again?

The claim is the status box. The ground truth is that the camera stops seeing
a live picture -- the camera runs on the Pi, so the feed dying IS the Pi
dying -- and that the Pi's own uptime went backwards afterwards.
"""

import re

import pytest

UPTIME = re.compile(r"([\d.]+)\s")


def _uptime_seconds(terminal, evidence, when: str) -> float:
    out = terminal.run("cat /proc/uptime")
    shown, detail = out.shows(".")
    evidence.ground_truth(f"the Pi reported its uptime {when}", shown, detail=detail)
    match = UPTIME.search(out.text)
    assert match, f"could not read an uptime from {out.text!r}"
    return float(match.group(1))


@pytest.mark.live
def test_reset_button_power_cycles_the_board(board_page, evidence):
    session = board_page("arty")
    board, page = session.board, session.page
    evidence_name = board.hostname

    detail = session.camera.wait_until_live(timeout=60)
    evidence.ground_truth(f"{evidence_name}'s camera feed is live before the reset", True, detail=detail)

    before = _uptime_seconds(session.terminal, evidence, "before the reset")

    page.click(f"#reset{board.port}")

    seen, detail = session.status.wait_for("power", timeout=30)
    evidence.claim("the status box reports the PoE port being switched", seen, detail=detail)

    detail = session.camera.wait_until_not_live(timeout=60)
    evidence.ground_truth(
        f"{evidence_name} stopped sending video, so it really lost power", True, detail=detail
    )

    detail = session.camera.wait_until_live(timeout=240)
    evidence.ground_truth(f"{evidence_name}'s camera feed came back", True, detail=detail)

    session.terminal.reconnect()
    after = _uptime_seconds(session.terminal, evidence, "after the reset")

    evidence.ground_truth(
        "the Pi's uptime went backwards, so it really rebooted",
        after < before,
        detail=f"before={before:.1f}s after={after:.1f}s",
    )
    evidence.ground_truth(
        "the Pi has only just booted",
        after < 240,
        detail=f"uptime after the reset was {after:.1f}s",
    )

    seen, detail = session.status.wait_for("ssh", timeout=120)
    evidence.claim("the status box reports the Pi's ssh server coming back", seen, detail=detail)
```

- [ ] **Step 2: Run it against production**

Run: `uv run pytest tests/shared/test_power_cycle.py --site welland -v -s`
Expected: PASS. The run prints the seed, the board it chose, and the evidence
summary. It power-cycles one Arty board; that is intended.

If the camera never reports live, check `$CHROMIUM --version` resolves to a
real chromium with H.264 -- a blank video element is the usual symptom of the
bundled Playwright browser being used by mistake.

- [ ] **Step 3: Commit**

```bash
git add tests/shared/test_power_cycle.py
git commit -m "Test: the Reset button really power-cycles the board"
```

---

## Task 10: Test 2 -- bitstream upload on an Arty

**Files:**
- Create: `$E2E/tests/shared/test_bitstream_upload.py`
- Create: `$E2E/fixtures/counter_test/top.bit`

**Interfaces:**
- Consumes: `board_page`, `evidence`.
- Produces: nothing other tasks use.

**Known failure.** `POST /pibup/upload` returns HTTP 500 on both sites,
because `pibup/views.py` reads `form.cleaned_data['run']` while
`pibup/forms.py` no longer defines a `run` field. This test will fail at the
success-page step. That is the suite doing its job; do not work around it.

To calibrate the later steps while the form is broken, put the bitstream on
the Pi by hand through the web terminal and run the programming and camera
assertions on their own. Do not change the test to do that.

- [ ] **Step 1: Add the bitstream fixture**

```bash
mkdir -p fixtures/counter_test
cp /home/tim/github/fpgas-online/fpgas.online-site/pibfpgas/Demos/counter_test/top.bit fixtures/counter_test/
```

Run: `ls -l fixtures/counter_test/top.bit`
Expected: 2192119 bytes.

- [ ] **Step 2: Write the test**

```python
"""Can a person upload a bitstream through the form and see it running?

The claim is the success page. The ground truth is that the file really landed
on the Pi at the right size, that openFPGALoader really programmed the part,
and that the LEDs visibly changed and are now counting.

Known limitation: counter_test/top.bit is the same bitstream the "Blink LEDs"
button loads, so the camera proves "the LEDs changed and are counting" but not
"this upload is what is running". A distinctive design from
fpgas.online-test-designs closes that gap later.
"""

from pathlib import Path

import pytest

BITSTREAM = Path(__file__).parents[2] / "fixtures" / "counter_test" / "top.bit"
REMOTE = "Uploads/top.bit"
LED_REGION = (0.0, 0.55, 1.0, 0.45)


@pytest.mark.live
def test_uploaded_bitstream_programs_the_arty_and_changes_the_leds(board_page, evidence):
    session = board_page("arty")
    page, terminal, camera = session.page, session.terminal, session.camera

    camera.wait_until_live(timeout=60)
    before = camera.shot()

    page.set_input_files("#upform input[type=file]", str(BITSTREAM))
    page.click("#upform input[type=submit]")
    page.wait_for_load_state("domcontentloaded")

    evidence.claim(
        "the upload form reports success",
        "uploaded" in page.content().lower(),
        detail=f"landed on {page.url} showing: {page.content()[:400]!r}",
    )

    page.go_back()
    terminal.reset()
    terminal.wait_for_prompt()

    listing = terminal.run(f"ls -l {REMOTE}")
    shown, detail = listing.shows(str(BITSTREAM.stat().st_size))
    evidence.ground_truth("the bitstream really landed on the Pi at the right size", shown, detail=detail)

    programming = terminal.run(f"openFPGALoader -b arty {REMOTE}", timeout=180)
    status = terminal.exit_status()
    evidence.ground_truth(
        "openFPGALoader programmed the FPGA",
        status == 0,
        detail=f"exit status {status}; output: {programming.text[-400:]!r}",
    )

    camera.wait_until_live(timeout=60)
    after = camera.shot()
    changed = _difference(before, after)
    evidence.ground_truth(
        "the LEDs look different from before the upload",
        changed > 0.02,
        detail=f"LED-region difference {changed:.4f}",
    )

    later = camera.shot()
    counting = _difference(after, later)
    evidence.ground_truth(
        "the LEDs are visibly counting, not frozen",
        counting > 0.005,
        detail=f"LED-region difference across two shots {counting:.4f}",
    )


def _difference(a, b):
    from e2e.camera import difference

    return difference(a, b, region=LED_REGION)
```

- [ ] **Step 3: Lint**

Run: `uv run ruff check tests/`
Expected: clean.

- [ ] **Step 4: Run it against production**

Run: `uv run pytest tests/shared/test_bitstream_upload.py --site welland -v -s`
Expected: **FAIL** at "the upload form reports success", because the form
returns HTTP 500. Record the failure output in the commit message. Do not
change the test.

- [ ] **Step 5: Commit**

```bash
git add tests/shared/test_bitstream_upload.py fixtures/counter_test/top.bit
git commit -m "Test: upload a bitstream through the form and see it running

Fails on both sites today: POST /pibup/upload returns 500 because
pibup/views.py reads form.cleaned_data['run'] and pibup/forms.py no
longer defines a run field."
```

---

## Task 11: Test 3 -- direct ssh per the instructions on the page

**Files:**
- Create: `$E2E/tests/shared/test_direct_ssh.py`
- Create: `$E2E/e2e/sshbanner.py`
- Test: `$E2E/tests/unit/test_sshbanner.py`

**Interfaces:**
- Consumes: `board_page`, `evidence`.
- Produces:
  - `parse_instructions(page_text: str) -> SshInstructions(user, host, port)`
  - `read_banner(host, port, timeout=15) -> str`
  - `password_from_banner(banner: str) -> str | None`

**Known failure.** The per-board ssh forward ports are unreachable on welland,
so this test fails there. It is expected to pass on ps1.

- [ ] **Step 1: Write the failing unit test**

`tests/unit/test_sshbanner.py`:

```python
import pytest

from e2e.sshbanner import parse_instructions, password_from_banner

PAGE = """
      Use your own ssh client. user: pi, host: welland.fpgas.online, port 21622,
      (password is in login banner)
      click to copy:
ssh -p 21622 pi@welland.fpgas.online
scp -P 21622 * pi@welland.fpgas.online:Uploads
"""


def test_parse_instructions_reads_user_host_and_port():
    got = parse_instructions(PAGE)
    assert (got.user, got.host, got.port) == ("pi", "welland.fpgas.online", 21622)


def test_parse_instructions_reads_the_copyable_ssh_command():
    assert parse_instructions(PAGE).ssh_command == "ssh -p 21622 pi@welland.fpgas.online"


def test_parse_instructions_raises_when_the_page_says_nothing():
    with pytest.raises(ValueError):
        parse_instructions("no instructions here")


@pytest.mark.parametrize(
    "banner, expected",
    [
        ("Welcome!\nThe password is hunter2\n", "hunter2"),
        ("password: swordfish", "swordfish"),
        ("Login with password 'let me in'", "let me in"),
    ],
)
def test_password_from_banner_finds_the_password(banner, expected):
    assert password_from_banner(banner) == expected


def test_password_from_banner_returns_none_when_there_is_none():
    assert password_from_banner("Debian GNU/Linux\n") is None
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/unit/test_sshbanner.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'e2e.sshbanner'`

- [ ] **Step 3: Write `e2e/sshbanner.py`**

```python
"""The 'use your own ssh client' instructions, and the banner they point at.

The board page tells the user a host, a port and that the password is in the
login banner. This module reads those instructions the way a person reads them
and then follows them.
"""

from __future__ import annotations

import dataclasses
import re
import socket

_DETAILS = re.compile(
    r"user:\s*(?P<user>\S+?),\s*host:\s*(?P<host>[\w.-]+),\s*port\s*(?P<port>\d+)",
    re.IGNORECASE,
)
_SSH_COMMAND = re.compile(r"ssh\s+-p\s*\d+\s+\S+@[\w.-]+")
_PASSWORD = re.compile(
    r"password(?:\s+is|:)?\s*[\"']?(?P<pw>[^\"'\r\n]+?)[\"']?\s*$",
    re.IGNORECASE | re.MULTILINE,
)


@dataclasses.dataclass(frozen=True)
class SshInstructions:
    user: str
    host: str
    port: int
    ssh_command: str


def parse_instructions(page_text: str) -> SshInstructions:
    match = _DETAILS.search(page_text)
    if match is None:
        raise ValueError("the page does not state a user, host and port for direct ssh")
    command = _SSH_COMMAND.search(page_text)
    return SshInstructions(
        user=match.group("user"),
        host=match.group("host"),
        port=int(match.group("port")),
        ssh_command=command.group(0) if command else "",
    )


def read_banner(host: str, port: int, timeout: float = 15.0) -> str:
    """Everything the server sends before authentication."""
    with socket.create_connection((host, port), timeout=timeout) as sock:
        sock.settimeout(timeout)
        chunks = []
        try:
            while len(b"".join(chunks)) < 8192:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                chunks.append(chunk)
        except TimeoutError:
            pass
    return b"".join(chunks).decode("utf-8", "replace")


def password_from_banner(banner: str) -> str | None:
    match = _PASSWORD.search(banner)
    return match.group("pw").strip() if match else None
```

- [ ] **Step 4: Run the unit test to verify it passes**

Run: `uv run pytest tests/unit/test_sshbanner.py -v`
Expected: 7 passed

- [ ] **Step 5: Write the live test**

`tests/shared/test_direct_ssh.py`:

```python
"""Do the ssh instructions printed on the board page actually work?

The page says: user pi, this host, this port, password in the login banner.
A person copies that, pastes it into a terminal, reads the banner, and logs
in. So does this test. The ground truth is a shell on the Pi that agrees with
the page about which board it is.
"""

import paramiko
import pytest

from e2e.sshbanner import parse_instructions, password_from_banner, read_banner


@pytest.mark.live
def test_ssh_instructions_on_the_page_let_you_log_in(board_page, evidence):
    session = board_page("arty")
    board, page, terminal = session.board, session.page, session.terminal

    instructions = parse_instructions(page.inner_text("body"))
    evidence.ground_truth(
        "the page tells the user how to ssh in",
        bool(instructions.ssh_command),
        detail=f"page says: {instructions}",
    )

    banner = read_banner(instructions.host, instructions.port)
    evidence.ground_truth(
        f"{instructions.host}:{instructions.port} answers",
        banner.startswith("SSH-"),
        detail=f"banner began: {banner[:120]!r}",
    )

    password = password_from_banner(banner)
    evidence.ground_truth(
        "the login banner contains the password, as the page promises",
        password is not None,
        detail=f"banner was: {banner[:400]!r}",
    )

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            instructions.host,
            port=instructions.port,
            username=instructions.user,
            password=password,
            timeout=20,
            allow_agent=False,
            look_for_keys=False,
        )
        _, stdout, _ = client.exec_command("hostname", timeout=20)
        remote_hostname = stdout.read().decode().strip()
    finally:
        client.close()

    evidence.ground_truth(
        "the credentials from the banner log in",
        bool(remote_hostname),
        detail=f"`hostname` returned {remote_hostname!r}",
    )
    evidence.ground_truth(
        "ssh reached the board the page said it would",
        remote_hostname == board.hostname,
        detail=f"page said {board.hostname!r}, ssh reached {remote_hostname!r}",
    )

    via_web = terminal.run("hostname")
    shown, detail = via_web.shows(remote_hostname)
    evidence.ground_truth(
        "the web terminal and direct ssh reach the same board", shown, detail=detail
    )
```

- [ ] **Step 6: Run it against both sites**

Run: `uv run pytest tests/shared/test_direct_ssh.py --site ps1 -v -s`
Expected: PASS (PS1's forward ports answer).

Run: `uv run pytest tests/shared/test_direct_ssh.py --site welland -v -s`
Expected: **FAIL** at "welland.fpgas.online:21622 answers" -- the port is
unreachable from the internet. Do not change the test.

- [ ] **Step 7: Commit**

```bash
git add e2e/sshbanner.py tests/unit/test_sshbanner.py tests/shared/test_direct_ssh.py
git commit -m "Test: the ssh instructions on the board page actually work

Passes on ps1. Fails on welland: the per-board forward ports it
advertises (21622, 24222, ...) are unreachable from the internet over
both IPv4 and IPv6, while welland.fpgas.online:22 answers."
```

---

## Task 12: The scheduled production run

**Files:**
- Create: `$E2E/.github/workflows/e2e.yml`

**Interfaces:**
- Consumes: everything.
- Produces: nothing.

- [ ] **Step 1: Write the workflow**

```yaml
name: e2e

on:
  schedule:
    - cron: "0 */6 * * *"
  workflow_dispatch:
    inputs:
      site:
        description: "Site to test (welland, ps1, or both)"
        default: both
        type: choice
        options: [both, welland, ps1]
      seed:
        description: "Replay a previous run's board choice"
        default: ""
      on_dead:
        description: "What to do if the chosen board is dead"
        default: fail
        type: choice
        options: [fail, retry]

jobs:
  unit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: sudo apt-get update && sudo apt-get install -y tesseract-ocr tesseract-ocr-eng fonts-dejavu-core
      - run: uv run pytest tests/unit -v

  shared:
    needs: unit
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        site: [welland, ps1]
    concurrency:
      group: e2e-${{ matrix.site }}
      cancel-in-progress: false
    if: >
      github.event_name != 'workflow_dispatch'
      || inputs.site == 'both'
      || inputs.site == matrix.site
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - name: Install the browser and OCR engine
        run: |
          sudo apt-get update
          sudo apt-get install -y chromium tesseract-ocr tesseract-ocr-eng fonts-dejavu-core
      - name: Run the suite against ${{ matrix.site }}
        env:
          CHROMIUM: /usr/bin/chromium
        run: |
          uv run pytest tests/shared -v -s \
            --site ${{ matrix.site }} \
            --on-dead ${{ inputs.on_dead || 'fail' }} \
            ${{ inputs.seed && format('--seed {0}', inputs.seed) || '' }} \
            --screenshot on --video retain-on-failure --tracing retain-on-failure \
            --output test-results
      - name: Upload artefacts
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: e2e-${{ matrix.site }}-${{ github.run_id }}
          path: test-results/
          retention-days: 14
```

- [ ] **Step 2: Verify the workflow parses**

Run: `uv run python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/e2e.yml')); print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit and push, then trigger a manual run**

```bash
git add .github/workflows/e2e.yml
git commit -m "Run the suite against production every six hours"
git push origin main
gh workflow run e2e.yml -f site=ps1 -f on_dead=retry
gh run watch
```

Expected: the `ps1` job runs. `test_direct_ssh` passes,
`test_bitstream_upload` fails as documented. Confirm the artefact was
uploaded and contains screenshots.

---

## Task 13: Roadmap document

**Files:**
- Create: `$E2E/docs/ROADMAP.md`
- Modify: `$E2E/tests/tinytapeout/README.md`

- [ ] **Step 1: Write `docs/ROADMAP.md`**

Copy the "Roadmap" section of
`docs/specs/2026-09-12-fpgas-online-e2e-tests-design.md` verbatim (Phase 1
table, Phase 1b, Phase 2, Phase 3), under a heading that says which tests
already exist:

```markdown
# Test roadmap

Implemented: power cycling, bitstream upload on an Arty, direct ssh per the
instructions on the board page.

The suite validates the *depth* of one path, not the breadth of identical
paths: if PoE control works on one board, it is not proven again on thirteen
more.

[... Phase 1 / 1b / 2 / 3 sections copied from the spec ...]

## Known production faults this suite reports

| Fault | Where | Since |
|---|---|---|
| Per-board ssh forward ports unreachable | welland | found 2026-09-12 |
| `POST /pibup/upload` returns 500 (`cleaned_data['run']` with no `run` field) | both | found 2026-09-12 |
| `/fpgas/tt.html` returns 404 (view hardcodes port 21) | both | found 2026-09-12 |
| PS1 runs the pre-split monorepo build | ps1 | known |
```

- [ ] **Step 2: Write `tests/tinytapeout/README.md`**

```markdown
# Tiny Tapeout tests (Phase 3)

`tinytapeout.fpgas.online` is a different application from `/fpgas/`, with its
own UI: catalogue cards, a status pill, `Power-cycle board`, `Reset video`,
the Commander embed's serial terminal over the RP2040 WebSocket bridge, the
design gallery served from the Pi daemon, Run/enable with a `clock_hz`, and a
`.bin` upload form with a 256 KiB cap and 16-file eviction.

Not yet implemented. See ../../docs/ROADMAP.md.
```

- [ ] **Step 3: Commit**

```bash
git add docs/ROADMAP.md tests/tinytapeout/README.md
git commit -m "Roadmap: the remaining UI audit, and the faults the suite already reports"
git push origin main
```

---

## Self-review notes

**Spec coverage.** Every spec section maps to a task: repository setup ->
Task 1; evidence model -> Task 2 (+ enforcement in Task 8); board discovery
and version skew -> Task 3; reading the terminal -> Tasks 4 and 6; reading
the camera -> Tasks 4 and 5; stack -> Tasks 1 and 8; the three tests ->
Tasks 9-11; selection and non-disruption -> Tasks 7 and 8 (and the
`toggle_all` prohibition, which appears nowhere in the code by construction);
CI -> Task 12; roadmap -> Task 13; running locally -> Task 1's README.

**Deliberate gap.** `tests/tinytapeout/` gets a README, not tests. Phase 3 is
a separate plan against a different application.

**Naming consistency.** `EvidenceLog.claim`/`.ground_truth` are used with
that spelling in Tasks 8-11. `Camera.shot`/`.is_live`/`.wait_until_live`/
`.wait_until_not_live` are used as defined in Task 5. `WebTerminal.run`/
`.exit_status`/`.reconnect`/`.wait_for_prompt`/`.attach` are used as defined
in Task 6. `Board.kind`/`.page_path` as defined in Task 3.
