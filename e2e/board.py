"""One FPGA board as the index page presents it."""

from __future__ import annotations

import dataclasses

# Matched in order, so a more specific name wins. An Acorn is never an Arty,
# and "TT FPGA emulation (iCE40UP5K)" must not fall through to unknown.
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
