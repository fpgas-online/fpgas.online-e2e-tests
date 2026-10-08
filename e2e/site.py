"""A deployment of the /fpgas/ application, and the boards it lists."""

from __future__ import annotations

import ast
import dataclasses
import html as htmllib
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
_FLEET_HREF = re.compile(r"^/fleet/[\w.-]+/$")


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


def parse_fleet_links(html: str) -> dict[str, str]:
    """Hostname -> the path of its fleet page, read off the /fleet/ list."""
    soup = BeautifulSoup(html, "html.parser")
    links = {}
    for link in soup.find_all("a", href=_FLEET_HREF):
        links[link.get_text().strip()] = link["href"]
    return links


def cameras_listed(fleet_page: str) -> bool | None:
    """Whether the board's latest hardware identification lists a camera.

    The fleet page of a board prints each identification the Pi reported as a
    Python dict, newest first, with `peripherals` -> `cameras` a list. True if
    the newest lists one or more, False if it lists none, None if the page has
    no identification or it cannot be read. None is never read as "no camera".
    """
    soup = BeautifulSoup(fleet_page, "html.parser")
    for details in soup.find_all("details"):
        pre = details.find("pre")
        if pre is None:
            continue
        try:
            cameras = ast.literal_eval(htmllib.unescape(pre.get_text()))["peripherals"]["cameras"]
        except (ValueError, SyntaxError, KeyError, TypeError):
            return None
        return bool(cameras) if isinstance(cameras, list) else None
    return None


def detect_cameras(boards: list[Board], fetch: Callable[[str], str]) -> list[Board]:
    """Each board with `has_camera` set from the site's fleet registry.

    `fetch(path)` returns the page text at a site path and raises when it
    cannot be read. Anything unreadable (the list, a board's page, a board the
    list does not name) leaves `has_camera` None, which the suite treats as a
    camera board: only the registry saying "no cameras" removes the camera
    step, so a camera board whose feed died still fails it. Cameras the Pi
    reports are what is connected, not whether the feed is live.
    """
    try:
        links = parse_fleet_links(fetch("/fleet/"))
    except Exception:  # noqa: BLE001 - an unreadable registry says nothing about any camera
        links = {}
    detected = []
    for board in boards:
        has_camera: bool | None = None
        if board.hostname in links:
            try:
                has_camera = cameras_listed(fetch(links[board.hostname]))
            except Exception:  # noqa: BLE001
                has_camera = None
        detected.append(dataclasses.replace(board, has_camera=has_camera))
    return detected


def page_fetcher(page, site: Site) -> Callable[[str], str]:
    """A `fetch(path)` for detect_cameras that reads the site through the browser's request context."""

    def fetch(path: str) -> str:
        response = page.request.get(site.url(path))
        if not response.ok:
            raise RuntimeError(f"{site.url(path)} answered {response.status}")
        return response.text()

    return fetch
