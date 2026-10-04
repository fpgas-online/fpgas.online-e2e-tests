"""A deployment of the /fpgas/ application, and the boards it lists."""

from __future__ import annotations

import dataclasses
import re

from bs4 import BeautifulSoup

from e2e.board import Board

SITES = {
    "welland": "https://welland.fpgas.online",
    "ps1": "https://ps1.fpgas.online",
}

# welland heads a card "pi-sw2-p46" and links pi-sw2-p46.html; ps1, still on the
# pre-split build, "FPGA pi2" and pi2.html.
_HOSTNAME_PREFIX = re.compile(r"^\s*FPGA\s+", re.IGNORECASE)
_PAGE_HREF = re.compile(r"^[\w.-]+\.html$")
_PLAYER_ID = re.compile(r"^video-player(\d+)$")


@dataclasses.dataclass(frozen=True)
class Site:
    name: str
    base_url: str

    @classmethod
    def from_name(cls, name: str) -> "Site":
        try:
            return cls(name, SITES[name])
        except KeyError:
            raise ValueError(f"unknown site {name!r}; known: {', '.join(sorted(SITES))}") from None

    @property
    def index_url(self) -> str:
        return f"{self.base_url}/fpgas/"

    def url(self, path: str) -> str:
        return f"{self.base_url}{path}"


def parse_boards(html: str) -> list[Board]:
    """Read the board cards off a rendered /fpgas/ page.

    Each card is a table whose first cell holds an <h1> with the hostname and
    (on current deployments) the FPGA name as trailing text, and whose second
    cell links to its <hostname>.html page. PS1 runs an older build whose heading reads
    "FPGA pi2" and which names no FPGA at all.
    """
    soup = BeautifulSoup(html, "html.parser")
    boards: list[Board] = []
    for link in soup.find_all("a", href=_PAGE_HREF):
        card = link.find_parent("table")
        if card is None:
            continue
        heading = card.find("h1")
        if heading is None:
            continue
        hostname = _HOSTNAME_PREFIX.sub("", heading.get_text()).strip()
        # The page is named by hostname, but the page's element ids carry the
        # switch port, which the card's own player id states.
        player = card.find(id=_PLAYER_ID)
        if player is None:
            raise ValueError(f"the card for {hostname!r} has no video-player<port> element to take the port from")
        port = int(_PLAYER_ID.match(player["id"]).group(1))
        fpga = "".join(s for s in heading.next_siblings if isinstance(s, str)).strip()
        boards.append(Board(hostname=hostname, port=port, fpga_board=fpga))
    return boards
