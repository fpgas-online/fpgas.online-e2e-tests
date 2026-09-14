"""Opening one board page the way a person does, with the primitives wired up.

Both the one-board-per-run fixture and the whole-site audit go through here,
so there is exactly one notion of "open this board" in the suite.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

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

    def snapshot(self, path: Path) -> None:
        """A full-page screenshot of the board page as it is now, for the record."""
        path.parent.mkdir(parents=True, exist_ok=True)
        self.page.screenshot(path=str(path), full_page=True)

    def close(self) -> None:
        if self.context is not None:
            self.context.close()


def open_board(browser, context_args: dict, site: Site, board: Board) -> BoardSession:
    """A fresh browser context on the board's page, which is what a person
    who opens a board page fresh gets.

    One context per board rather than one for the run, so that nothing the
    browser accumulated on the last board is blamed on this one. Playwright's
    bundled Chromium never recovered a failed player on the next page (ps1:
    pi7 live, pi9 live, then pi2 dead and pi7 dead again); real Chrome does,
    and the suite now runs real Chrome, but a board's verdict should still
    not depend on which board came before it.
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
