from pathlib import Path

import pytest

from e2e.board import Board
from e2e.site import Site, cameras_listed, detect_cameras, parse_boards, parse_fleet_links

FIXTURES = Path(__file__).parents[2] / "fixtures" / "html"


@pytest.fixture
def welland_boards():
    return parse_boards((FIXTURES / "welland-fpgas-index-2026-10-04.html").read_text())


@pytest.fixture
def ps1_boards():
    return parse_boards((FIXTURES / "ps1-fpgas-index-2026-10-04.html").read_text())


def test_welland_snapshot_lists_boards_by_hostname(welland_boards):
    """A frozen snapshot of the index, so its contents are fixed; the live site's are not."""
    assert [b.hostname for b in welland_boards] == ["pi-sw2-p46", "pi-sw2-p47"]


def test_welland_board_carries_hostname_port_and_fpga(welland_boards):
    first = welland_boards[0]
    assert first.hostname == "pi-sw2-p46"
    assert first.port == 46
    assert first.fpga_board == "Acorn (cle-215+)"


def test_welland_board_page_is_named_by_hostname(welland_boards):
    assert welland_boards[0].page_path == "/fpgas/pi-sw2-p46.html"


def test_the_port_comes_from_the_card_not_the_hostname():
    html = """
    <table><tr><td><h1>pi-sw9-p3</h1>Some FPGA</td></tr>
    <tr><td><a href="pi-sw9-p3.html">Use this FPGA</a></td></tr>
    <tr><td><video id="video-player77"></video></td></tr></table>
    """
    (board,) = parse_boards(html)
    assert (board.hostname, board.port) == ("pi-sw9-p3", 77)


def test_a_card_without_a_player_id_is_an_error():
    html = '<table><tr><td><h1>pi-sw9-p3</h1>X</td></tr><tr><td><a href="pi-sw9-p3.html">go</a></td></tr></table>'
    with pytest.raises(ValueError, match="pi-sw9-p3"):
        parse_boards(html)


def test_ps1_snapshot_uses_the_older_heading_format(ps1_boards):
    assert [b.hostname for b in ps1_boards][:2] == ["pi2", "pi3"]
    assert ps1_boards[0].port == 2
    assert ps1_boards[0].page_path == "/fpgas/pi2.html"
    assert ps1_boards[0].fpga_board == ""


def test_fpga_type_is_read_from_what_the_site_shows(welland_boards, ps1_boards):
    assert welland_boards[0].fpga_type == "acorn"
    assert ps1_boards[0].fpga_type == "unknown"


@pytest.mark.parametrize(
    ("shown", "kind"),
    [
        ("Digilent Arty A7-35T", "arty"),
        ("Sqrl Acorn CLE-215+", "acorn"),
        ("Acorn (cle-215+)", "acorn"),
        ("TT FPGA emulation (iCE40UP5K)", "unknown"),
        ("", "unknown"),
    ],
)
def test_fpga_type_classification(shown, kind):
    from e2e.board import Board

    assert Board("h", 1, shown).fpga_type == kind


def test_site_from_name_builds_the_base_url():
    assert Site.from_name("welland").base_url == "https://welland.fpgas.online"
    assert Site.from_name("ps1").index_url == "https://ps1.fpgas.online/fpgas/"


def test_site_from_name_rejects_an_unknown_site():
    with pytest.raises(ValueError):
        Site.from_name("nowhere")


# -- cameras, from the fleet registry --------------------------------------------------------------------------

FLEET_BOARD = (FIXTURES / "welland-fleet-board-no-cameras-2026-10-08.html").read_text()
_NONE = "&#x27;cameras&#x27;: []"
WITH_CAMERA = FLEET_BOARD.replace(_NONE, _NONE.replace("[]", "[{}]"), 1)


def test_the_fleet_list_maps_hostnames_to_their_pages():
    links = parse_fleet_links((FIXTURES / "welland-fleet-2026-10-04.html").read_text())
    assert links["pi-sw1-p17"] == "/fleet/00000000cc479fd1/"
    assert links["pi-sw2-p43"] == "/fleet/a01e40441f959c20/"


def test_an_empty_cameras_list_in_the_newest_identification_means_no_camera():
    """The older identification in the fixture lists a camera; only the newest counts."""
    assert cameras_listed(FLEET_BOARD) is False


def test_a_listed_camera_in_the_newest_identification_means_a_camera():
    assert cameras_listed(WITH_CAMERA) is True


@pytest.mark.parametrize(
    "page",
    ["<html><h1>pi-sw1-p17</h1><p>no usable pi-identified event from this Pi</p></html>", "<pre>{</pre>", ""],
)
def test_a_page_without_a_readable_identification_is_unknown(page):
    assert cameras_listed(page) is None
    assert cameras_listed(page.replace("<pre>", "<details><pre>")) is None


def _fetcher(pages):
    def fetch(path):
        if isinstance(pages.get(path), Exception):
            raise pages[path]
        return pages[path]

    return fetch


def test_detect_cameras_reads_each_boards_own_fleet_page():
    pages = {
        "/fleet/": (FIXTURES / "welland-fleet-2026-10-04.html").read_text(),
        "/fleet/00000000cc479fd1/": FLEET_BOARD,
        "/fleet/a01e40441f959c20/": WITH_CAMERA,
    }
    boards = [Board("pi-sw1-p17", 17, ""), Board("pi-sw2-p43", 43, "")]
    assert [b.has_camera for b in detect_cameras(boards, _fetcher(pages))] == [False, True]


def test_detect_cameras_leaves_unknown_what_it_cannot_read_and_never_says_no_camera():
    pages = {
        "/fleet/": (FIXTURES / "welland-fleet-2026-10-04.html").read_text(),
        "/fleet/00000000cc479fd1/": ConnectionError("down"),
    }
    boards = [Board("pi-sw1-p17", 17, ""), Board("not-listed", 1, "")]
    assert [b.has_camera for b in detect_cameras(boards, _fetcher(pages))] == [None, None]


def test_detect_cameras_with_an_unreadable_fleet_list_leaves_every_board_unknown():
    boards = [Board("pi-sw1-p17", 17, "")]
    assert [b.has_camera for b in detect_cameras(boards, _fetcher({"/fleet/": RuntimeError("500")}))] == [None]
