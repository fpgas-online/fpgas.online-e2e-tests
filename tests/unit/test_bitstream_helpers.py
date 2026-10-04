import time
from pathlib import Path

from e2e.board import Board
from e2e.site import parse_boards
from tests.shared.test_bitstream_upload import _recently_written, loadable_for

INDEX = Path(__file__).parents[2] / "fixtures" / "html" / "welland-fpgas-index-2026-10-04.html"


def test_a_file_written_just_now_counts_as_fresh():
    text = f"2026-09-13T11:02\n{int(time.time())}\n"
    fresh, detail = _recently_written(text)
    assert fresh, detail


def test_yesterdays_file_does_not_count():
    """The identical bitstream from a previous run satisfies a size check.

    Only the timestamp distinguishes "this upload landed" from "a file with
    the right size is sitting there", which is what the test claims to prove.
    """
    text = f"2026-09-13T11:02\n{int(time.time()) - 86400}\n"
    fresh, detail = _recently_written(text)
    assert not fresh
    assert "old" in detail


def test_an_unreadable_listing_is_not_fresh():
    fresh, detail = _recently_written("ls: cannot access: No such file or directory")
    assert not fresh
    assert "could not read an mtime" in detail


def test_an_arty_has_a_bitstream_and_loader_arguments():
    bitstream, args = loadable_for(Board("h", 1, "Digilent Arty A7-35T"))
    assert bitstream.exists()
    assert args == "-b arty"


def test_the_acorns_the_site_offers_have_no_fixture_so_the_test_must_skip():
    boards = parse_boards(INDEX.read_text())
    assert boards
    assert all(b.fpga_type == "acorn" for b in boards)
    assert all(loadable_for(b) is None for b in boards)
