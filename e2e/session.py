"""Opening one board page the way a person does, with the primitives wired up.

Both the one-board-per-run fixture and the whole-site audit go through here,
so there is exactly one notion of "open this board" in the suite.
"""

from __future__ import annotations

import dataclasses

from e2e.board import Board
from e2e.camera import Camera
from e2e.site import Site
from e2e.statuslog import StatusLog
from e2e.terminal import WebTerminal


@dataclasses.dataclass
class BoardSession:
    board: Board
    page: object
    terminal: WebTerminal
    camera: Camera
    status: StatusLog
    context: object = None

    def close(self) -> None:
        if self.context is not None:
            self.context.close()


def open_board(browser, context_args: dict, site: Site, board: Board) -> BoardSession:
    """A fresh browser context on the board's page, which is what a person
    who opens a board page fresh gets.

    Reusing one browser context leaves the video player dead from about the
    third board page onward -- measured against ps1: pi7 live, pi9 live, then
    pi2 dead and pi7 dead again, readyState 0 and paused, on streams that
    serve fine. A new tab in the same context is not enough; the breakage
    outlives the page. Visiting boards through a poisoned context blames each
    board in turn for a fault that belongs to the browsing session.
    """
    context = browser.new_context(**context_args)
    page = context.new_page()
    terminal = WebTerminal(page)
    terminal.attach()
    page.goto(site.url(board.page_path), wait_until="domcontentloaded")
    return BoardSession(
        board=board,
        page=page,
        terminal=terminal,
        camera=Camera(page, f"#video-player{board.port}"),
        status=StatusLog(page, board.port),
        context=context,
    )
