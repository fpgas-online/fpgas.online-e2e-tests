from pathlib import Path

import pytest

from e2e.site import Site, parse_boards

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
