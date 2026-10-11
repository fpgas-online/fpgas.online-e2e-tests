"""A deployment of the /fpgas/ application, and the boards it lists."""

from __future__ import annotations

import dataclasses
import json
import re
from collections.abc import Callable

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


def cameras_by_hostname(text: str) -> dict[str, bool | None]:
    """Hostname -> whether its newest registration lists a camera, from the site's /fleet/registry.json.

    True if `cameras` lists one or more, False if it is an empty list, None if
    the site does not say (null, or not a list). None is never read as "no
    camera". A text that is not the registry document gives {}: it says
    nothing about any camera.
    """
    try:
        machines = json.loads(text)["machines"]
    except (ValueError, KeyError, TypeError):
        return {}
    found: dict[str, bool | None] = {}
    for machine in machines if isinstance(machines, list) else []:
        if not isinstance(machine, dict) or not isinstance(machine.get("hostname"), str):
            continue
        cameras = machine.get("cameras")
        hostname, says = machine["hostname"].strip(), bool(cameras) if isinstance(cameras, list) else None
        # two machines on one hostname that disagree say nothing certain: "not known", never "no camera"
        found[hostname] = says if found.get(hostname, says) == says else None
    return found


def detect_cameras(boards: list[Board], fetch: Callable[[str], str]) -> list[Board]:
    """Each board with `has_camera` set from the site's fleet registry.

    `fetch(path)` returns the text at a site path and raises when it cannot
    be read. Anything unreadable (the registry, a board it does not name, a
    board it says nothing of) leaves `has_camera` None, which the suite treats
    as a camera board: only the registry saying "no cameras" removes the camera
    step, so a camera board whose feed died still fails it. Cameras the Pi
    reports are what is connected, not whether the feed is live.
    """
    try:
        cameras = cameras_by_hostname(fetch("/fleet/registry.json"))
    except Exception:  # noqa: BLE001 - an unreadable registry says nothing about any camera
        cameras = {}
    return [dataclasses.replace(board, has_camera=cameras.get(board.hostname)) for board in boards]


def page_fetcher(page, site: Site) -> Callable[[str], str]:
    """A `fetch(path)` for detect_cameras that reads the site through the browser's request context."""

    def fetch(path: str) -> str:
        response = page.request.get(site.url(path))
        if not response.ok:
            raise RuntimeError(f"{site.url(path)} answered {response.status}")
        return response.text()

    return fetch
