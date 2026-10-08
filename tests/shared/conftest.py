"""The board_page factory: pick a board, open it, and wire up the primitives."""

from __future__ import annotations

import pytest

from e2e.picker import OnDead, choose, why_picked
from e2e.session import BoardSession, open_board
from e2e.site import parse_boards, probe_cameras
from e2e.terminal import TerminalBusy
from tests.busy import skip_for_busy_terminal


@pytest.fixture
def board_page(
    request,
    browser,
    browser_context_args,
    browser_identity,
    page,
    site,
    seed,
    on_dead,
    evidence,
    output_dir,
    boards_wanted,
    disruption_guard,
):
    """Factory: board_page() -> BoardSession on a live, working board.

    Any board the index lists will do, and what FPGA it is comes from what the
    index shows (Board.fpga_type).
    Every board page opened is screenshotted and closed when the test ends,
    whatever happened: pytest-playwright only records its own context, and
    every failure happens on ours.
    """
    opened: list[BoardSession] = []
    disruptive_test = request.node.get_closest_marker("disruptive") is not None

    def _open() -> BoardSession:
        page.goto(site.index_url, wait_until="domcontentloaded")
        boards = probe_cameras(parse_boards(page.content()), lambda url: page.request.get(url).status)
        # A claim, not ground truth: this is the site talking about itself.
        # Recording it as ground truth satisfied has_ground_truth for every
        # live test before its body ran, which disarmed the one guard the
        # suite has against passing on claims alone.
        evidence.claim(
            "the index page lists at least one board",
            bool(boards),
            detail=f"listed: {[(b.hostname, b.fpga_board) for b in boards]}",
        )

        if disruptive_test and not boards_wanted:
            pytest.fail("a disruptive test never chooses its board: run it with --boards <hostname>", pytrace=False)
        candidates = choose(boards, seed, wanted=boards_wanted)
        problems = []
        for board in candidates:
            if disruptive_test:
                # Before the board's page is even opened, and for a board that was named explicitly too.
                refusal = disruption_guard.refusal(board)
                if refusal:
                    pytest.fail(f"refused: {refusal}", pytrace=False)
            session = open_board(browser, browser_context_args, site, board)
            if disruptive_test:
                session.refusal_check = lambda board=board: disruption_guard.refusal(board)
            opened.append(session)
            print(f"[e2e] {why_picked(board, boards, seed, boards_wanted)}")
            try:
                ok, why = _is_working(session)
            except TerminalBusy as exc:
                # A visitor is typing: skip with the reason. A terminal with no
                # prompt at all is dead, and still lands in `problems` below.
                skip_for_busy_terminal(evidence, exc)
            if ok:
                print(f"[e2e] testing on {board.hostname} ({board.fpga_board})")
                if problems:
                    # --on-dead retry lets the test run on a working board so
                    # that the deep check still happens; it does not make the
                    # dead ones disappear. Recorded as a claim that failed,
                    # so the ledger shows them and the run stays red.
                    evidence.claim(
                        "every board tried was working",
                        False,
                        detail="skipped: " + "; ".join(problems),
                    )
                return session
            problems.append(f"{board.hostname}: {why}")
            print(f"[e2e] {board.hostname} is not usable: {why}")
            if on_dead is OnDead.FAIL:
                break
        raise AssertionError("no usable board.\n  " + "\n  ".join(problems) + f"\n(--on-dead={on_dead.value})")

    def _is_working(session) -> tuple[bool, str]:
        """The glance a person gives a board before deciding to use it.

        The camera first, then the terminal: a visitor on the terminal skips
        the test (TerminalBusy propagates), and that must never be reachable
        for a board whose picture is dead.
        """
        # Wait for the picture rather than sampling it once. video.js has to
        # fetch the playlist, buffer a few one-second segments and start
        # decoding; a single sample taken the moment the terminal connects
        # catches readyState 0 every time and calls a healthy board dead.
        if session.board.has_camera is False:
            # Tested for what it has: the page, the web terminal and ssh. A
            # board with a camera that is slow is still a failure, below.
            return _terminal_ready(session, "no camera on this board")
        try:
            live, detail = session.camera.check_live_with_recovery(timeout=45)
        except Exception as exc:  # noqa: BLE001
            return False, f"the camera could not be read ({exc})"
        if not live:
            return False, f"the camera feed never went live ({detail})"
        return _terminal_ready(session, f"the camera feed is live ({detail})")

    def _terminal_ready(session, ok_detail: str) -> tuple[bool, str]:
        try:
            session.terminal.wait_for_prompt(timeout=45)
        except TimeoutError as exc:
            return False, f"the web terminal never reached a prompt ({exc})"
        return True, ok_detail

    yield _open

    for session in opened:
        try:
            session.snapshot(output_dir / request.node.name / f"{session.board.hostname}.png")
        except Exception as exc:  # noqa: BLE001 - a page that is gone still has to be closed
            print(f"[e2e] no screenshot of {session.board.hostname}: {exc}")
        session.close()
