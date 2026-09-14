"""The board_page factory: pick a board, open it, and wire up the primitives."""

from __future__ import annotations

import pytest

from e2e.picker import OnDead, choose
from e2e.session import BoardSession, open_board
from e2e.site import parse_boards


@pytest.fixture
def board_page(browser, browser_context_args, page, site, seed, on_dead, evidence):
    """Factory: board_page() -> BoardSession on a live, working board.

    Any board the index lists will do, and every one is assumed to be an Arty.
    """

    def _open() -> BoardSession:
        page.goto(site.index_url, wait_until="domcontentloaded")
        boards = parse_boards(page.content())
        # A claim, not ground truth: this is the site talking about itself.
        # Recording it as ground truth satisfied has_ground_truth for every
        # live test before its body ran, which disarmed the one guard the
        # suite has against passing on claims alone.
        evidence.claim(
            "the index page lists at least one board",
            bool(boards),
            detail=f"listed: {[(b.hostname, b.fpga_board) for b in boards]}",
        )

        candidates = choose(boards, seed)
        problems = []
        for board in candidates:
            session = open_board(browser, browser_context_args, site, board)
            ok, why = _is_working(session)
            if ok:
                print(f"[e2e] testing on {board.hostname} ({board.fpga_board})")
                return session
            problems.append(f"{board.hostname}: {why}")
            session.close()
            if on_dead is OnDead.FAIL:
                break
        raise AssertionError(
            "no usable board.\n  " + "\n  ".join(problems) + f"\n(--on-dead={on_dead.value})"
        )

    def _is_working(session) -> tuple[bool, str]:
        """The glance a person gives a board before deciding to use it."""
        try:
            session.terminal.wait_for_prompt(timeout=45)
        except TimeoutError as exc:
            return False, f"the web terminal never reached a prompt ({exc})"
        # Wait for the picture rather than sampling it once. video.js has to
        # fetch the playlist, buffer a few one-second segments and start
        # decoding; a single sample taken the moment the terminal connects
        # catches readyState 0 every time and calls a healthy board dead.
        try:
            live, detail = session.camera.check_live_with_recovery(timeout=45)
            return live, (
                f"the camera feed is live ({detail})" if live else f"the camera feed never went live ({detail})"
            )
        except Exception as exc:  # noqa: BLE001
            return False, f"the camera could not be read ({exc})"

    return _open
