"""Every board at the site, checked the way a person with a checklist would.

One row per board, one column per thing a user needs to work: the page, the
camera, the web terminal, the PoE status the page reports, the ssh
instructions, and the Reset button. The table is printed at the end and
written to the output directory; on GitHub it also lands in the job summary.

By default it changes nothing on the boards: the upload and the power cycle
are reported as skipped ("needs --disruptive"). With --disruptive every board
gets reprogrammed (where its FPGA type has a bitstream here) and power cycled,
which takes the best part of an hour per site and interrupts anyone using the
board, which is why it is not on the six-hourly schedule. Run it by hand:

    uv run pytest tests/audit --site ps1 -s
    uv run pytest tests/audit --site ps1 -s --disruptive
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from e2e.audit import audit_board, render_markdown, render_text, unopened_board_audit
from e2e.session import open_board
from e2e.site import detect_cameras, page_fetcher, parse_boards


@pytest.mark.live
def test_every_board_at_the_site(
    browser,
    browser_context_args,
    browser_identity,
    page,
    site,
    boards_wanted,
    known_hosts,
    output_dir,
    evidence,
    disruptive,
    disruption_guard,
):
    page.goto(site.index_url, wait_until="domcontentloaded")
    boards = detect_cameras(parse_boards(page.content()), page_fetcher(page, site))
    assert boards, f"the index page at {site.index_url} lists no boards, so there is nothing to audit"
    evidence.claim(
        "the index page lists at least one board",
        True,
        detail=f"listed: {[b.hostname for b in boards]}",
    )
    if boards_wanted:
        boards = [b for b in boards if b.hostname in boards_wanted]
        assert boards, f"--boards {sorted(boards_wanted)} matched none of the boards the index lists"

    rows = []
    print(f"\n[audit] {site.name}: {len(boards)} boards", flush=True)
    for board in boards:
        try:
            session = open_board(browser, browser_context_args, site, board)
        except Exception as exc:  # noqa: BLE001 - a page that will not open is this board's row, not the run's end
            row = unopened_board_audit(board, exc)
            rows.append(row)
            print(f"[audit] {board.hostname}: {row.check('page').detail}", flush=True)
            continue
        try:
            row = audit_board(
                session, known_hosts, disruptive=disruptive, refusal=lambda board=board: disruption_guard.refusal(board)
            )
        finally:
            try:
                session.snapshot(output_dir / f"audit-{site.name}" / f"{board.hostname}.png")
            except Exception as exc:  # noqa: BLE001 - a page that is gone still has to be closed
                print(f"[audit] no screenshot of {board.hostname}: {exc}")
            session.close()
        rows.append(row)
        cells = "  ".join(f"{c.name}={c.timed}" for c in row.checks)
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
