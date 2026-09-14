"""Every board at the site, checked the way a person with a checklist would.

One row per board, one column per thing a user needs to work: the page, the
camera, the web terminal, the PoE status the page reports, the ssh
instructions, and the Reset button. The table is printed at the end and
written to the output directory; on GitHub it also lands in the job summary.

This is deliberately disruptive -- every board gets power cycled -- and takes
the best part of an hour per site, which is why it is not on the six-hourly
schedule. Run it by hand:

    uv run pytest tests/audit --site ps1 -s
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from e2e.audit import audit_board, render_markdown, render_text
from e2e.session import open_board
from e2e.site import parse_boards


@pytest.mark.live
def test_every_board_at_the_site(
    browser, browser_context_args, page, site, boards_wanted, known_hosts, output_dir, evidence
):
    page.goto(site.index_url, wait_until="domcontentloaded")
    boards = parse_boards(page.content())
    evidence.claim(
        "the index page lists at least one board",
        bool(boards),
        detail=f"listed: {[b.hostname for b in boards]}",
    )
    if boards_wanted:
        boards = [b for b in boards if b.hostname in boards_wanted or f"pi{b.port}" in boards_wanted]
        assert boards, f"--boards {sorted(boards_wanted)} matched none of the boards the index lists"

    rows = []
    print(f"\n[audit] {site.name}: {len(boards)} boards", flush=True)
    for board in boards:
        session = open_board(browser, browser_context_args, site, board)
        try:
            row = audit_board(session, known_hosts)
        finally:
            session.close()
        rows.append(row)
        cells = "  ".join(f"{c.name}={c.cell}" for c in row.checks)
        print(f"[audit] {board.hostname}: {cells}", flush=True)

    table = render_text(site.name, rows)
    print(f"\n{table}\n", flush=True)
    report = output_dir / f"audit-{site.name}.md"
    report.write_text(render_markdown(site.name, rows))
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with Path(summary).open("a") as handle:
            handle.write(render_markdown(site.name, rows))

    failures = [(row.board.hostname, check) for row in rows for check in row.failures]
    evidence.ground_truth(
        f"every check passed on every one of {site.name}'s {len(rows)} boards",
        not failures,
        detail=f"{len(failures)} failing cells, see the table above and {report}" if failures else table,
    )
