from pathlib import Path

import pytest

from e2e.site import Site, parse_boards

FIXTURES = Path(__file__).parents[2] / "fixtures" / "html"


@pytest.fixture
def welland_boards():
    return parse_boards((FIXTURES / "welland-fpgas-index.html").read_text())


@pytest.fixture
def ps1_boards():
    return parse_boards((FIXTURES / "ps1-fpgas-index.html").read_text())


def test_welland_index_lists_fourteen_boards(welland_boards):
    assert len(welland_boards) == 14


def test_welland_board_carries_hostname_port_and_fpga(welland_boards):
    first = welland_boards[0]
    assert first.hostname == "pi-sw2-p16"
    assert first.port == 16
    assert first.fpga_board == "Digilent Arty A7-35T"


def test_ps1_index_lists_nine_boards_with_the_older_heading_format(ps1_boards):
    assert len(ps1_boards) == 9
    assert ps1_boards[0].hostname == "pi2"
    assert ps1_boards[0].port == 2


def test_board_kind_is_derived_from_the_fpga_name(welland_boards):
    kinds = {b.hostname: b.kind for b in welland_boards}
    assert kinds["pi-sw2-p16"] == "arty"
    assert kinds["pi-sw2-p29"] == "acorn"
    assert kinds["pi-sw2-p33"] == "tt"


def test_a_board_with_no_fpga_named_is_unknown_kind(ps1_boards):
    assert ps1_boards[0].kind == "unknown"


def test_page_path_uses_the_port_not_the_hostname(welland_boards):
    assert welland_boards[0].page_path == "/fpgas/pi16.html"


def test_site_from_name_builds_the_base_url():
    assert Site.from_name("welland").base_url == "https://welland.fpgas.online"
    assert Site.from_name("ps1").index_url == "https://ps1.fpgas.online/fpgas/"


def test_site_from_name_rejects_an_unknown_site():
    with pytest.raises(ValueError):
        Site.from_name("nowhere")
