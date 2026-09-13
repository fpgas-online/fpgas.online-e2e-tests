"""One FPGA board as the index page presents it."""

from __future__ import annotations

import dataclasses


@dataclasses.dataclass(frozen=True)
class Board:
    hostname: str
    port: int
    fpga_board: str

    @property
    def page_path(self) -> str:
        """The per-board page, which is addressed by switch port, not hostname."""
        return f"/fpgas/pi{self.port}.html"
