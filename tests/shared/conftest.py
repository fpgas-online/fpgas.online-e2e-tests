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
        """The glance a person gives a board before deciding to use it."""
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
