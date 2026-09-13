import pytest

from e2e.board import Board
from e2e.picker import NoSuchBoard, OnDead, choose

BOARDS = [
    Board("pi-sw2-p16", 16, "Digilent Arty A7-35T"),
    Board("pi-sw2-p29", 29, "Sqrl Acorn CLE-215+"),
    Board("pi-sw2-p37", 37, "Digilent Arty A7-35T"),
    Board("pi-sw2-p33", 33, "TT FPGA emulation (iCE40UP5K)"),
]


def test_choose_offers_every_board_the_site_lists():
    """No filtering by advertised FPGA type: ps1 names none, so filtering tested nothing."""
    assert {b.port for b in choose(BOARDS, seed=1)} == {16, 29, 33, 37}


def test_choose_is_deterministic_for_a_given_seed():
    assert [b.port for b in choose(BOARDS, seed=7)] == [b.port for b in choose(BOARDS, seed=7)]


def test_choose_shuffles_so_different_seeds_can_give_different_orders():
    orders = {tuple(b.port for b in choose(BOARDS, seed=s)) for s in range(20)}
    assert len(orders) > 1


def test_choose_raises_when_the_site_lists_no_boards():
    with pytest.raises(NoSuchBoard):
        choose([], seed=1)


def test_on_dead_parses_from_the_command_line_values():
    assert OnDead("fail") is OnDead.FAIL
    assert OnDead("retry") is OnDead.RETRY
