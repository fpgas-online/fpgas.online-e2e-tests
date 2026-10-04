"""Failures that are known and tracked, so a schedule that is red stays a signal.

One table: (site, test) -> why it fails, with the issue that tracks it. The
entry is applied in one place (`pytest_collection_modifyitems` in
tests/conftest.py) as a STRICT expected failure, narrowed to the one kind of
failure that was investigated. So:

- the day the thing works, the test passes unexpectedly and the run goes red
  (XPASS strict): that is the cue to delete the entry;
- any other failure of the same test (a dead camera, a page that does not
  load, the wrong hostname) is not the expected one and still fails the run.

An entry naming a test that does not exist is an error, so the table cannot
rot silently.
"""

from __future__ import annotations

import ast
import dataclasses
from pathlib import Path

import pytest

from e2e.journeys import SshBannerHasNoPassword


@dataclasses.dataclass(frozen=True)
class KnownFailure:
    reason: str  # must contain the URL of the issue that tracks it
    raises: type[BaseException]  # the only failure that is expected


class UnknownKnownFailure(pytest.UsageError):
    """The table names a test that is not there."""


# The repository root, which the table's paths are relative to.
ROOT = Path(__file__).parents[1]

# Keys: (site name, "<path of the test file from the repository root>::<test function>").
KNOWN_FAILURES: dict[tuple[str, str], KnownFailure] = {
    ("welland", "tests/shared/test_direct_ssh.py::test_ssh_instructions_on_the_page_let_you_log_in"): KnownFailure(
        reason=(
            "the board's sshd shows no banner with the password, so the page's instruction "
            "('password is in login banner') cannot be followed: the printed ssh command reaches the "
            "password prompt and the visitor was never shown a password. Tracked in "
            "fpgas-online/fpgas.online-infra#215 (https://github.com/fpgas-online/fpgas.online-infra/issues/215). "
            "Remove this entry when the boards' root carries the ssh banner"
        ),
        raises=SshBannerHasNoPassword,
    ),
}


def _defines(path: Path, function: str) -> bool:
    tree = ast.parse(path.read_text(), filename=str(path))
    return any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function for node in tree.body
    )


def validate(table: dict[tuple[str, str], KnownFailure], root: Path) -> None:
    """Every entry must name a test function that exists under `root`, found in the file, not by collecting."""
    for (site, test), _entry in table.items():
        file, _, function = test.partition("::")
        path = root / file
        if not function or not path.is_file() or not _defines(path, function):
            raise UnknownKnownFailure(f"known failure for {site} names a test that does not exist: {test}")


def apply(items, site: str) -> None:
    """Mark each item the table lists for `site` as a strict expected failure of its one expected kind.

    `site` is the run's --site: a matrix is one run per site, so each run gets
    only its own site's entries.
    """
    root, table = ROOT, KNOWN_FAILURES  # read now, so a test can substitute them
    validate(table, root)
    for item in items:
        try:
            relative = item.path.relative_to(root).as_posix()
        except ValueError:
            continue
        entry = table.get((site, f"{relative}::{getattr(item, 'originalname', item.name)}"))
        if entry is not None:
            item.add_marker(pytest.mark.xfail(strict=True, reason=entry.reason, raises=entry.raises))
