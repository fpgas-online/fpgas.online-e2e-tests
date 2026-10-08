"""One FPGA board as the index page presents it."""

from __future__ import annotations

import dataclasses


@dataclasses.dataclass(frozen=True)
class Board:
    """A board is identified by its hostname; the port is only where it is plugged in."""

    hostname: str
    port: int
    fpga_board: str
    # The HLS playlist the index card plays; "" when the card names none (ps1).
    stream_url: str = ""
    # Whether the board has a camera: True or False once the stream has been
    # looked at (e2e.site.probe_cameras), None while nobody has looked. The
    # index and board pages show a video player for every board, camera or
    # not, so only observation can say.
    has_camera: bool | None = None

    @property
    def page_path(self) -> str:
        """The per-board page, which is named by hostname.

        The element ids on that page (video-player, reset, status) still use
        the switch port, which is why `port` is carried separately.
        """
        return f"/fpgas/{self.hostname}.html"

    @property
    def fpga_type(self) -> str:
        """The family of FPGA the site says is fitted: "arty", "acorn" or "unknown".

        Derived only from the text the index shows for this board. A board
        whose type is not recognised, or which the site does not describe
        (ps1), is "unknown" rather than guessed at.
        """
        shown = self.fpga_board.lower()
        for family in ("arty", "acorn"):
            if family in shown:
                return family
        return "unknown"
