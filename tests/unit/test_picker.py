import pytest

from e2e.board import Board
from e2e.picker import NoSuchBoard, OnDead, choose, why_picked

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


# -- cameras: a board with one is picked first ------------------------------------------------------------------


def _cam(hostname, port, has_camera):
    return Board(hostname, port, "", has_camera=has_camera)


MIXED = [
    _cam("pi-sw2-p10", 10, False),
    _cam("pi-sw2-p11", 11, True),
    _cam("pi-sw2-p12", 12, None),
    _cam("pi-sw2-p13", 13, True),
    _cam("pi-sw2-p14", 14, False),
    _cam("pi-sw2-p15", 15, True),
]


@pytest.mark.parametrize("seed", range(30))
def test_boards_with_a_camera_come_first_then_unknown_then_none(seed):
    order = [b.has_camera for b in choose(MIXED, seed=seed)]
    assert order == [True, True, True, None, False, False]


def test_the_seed_still_shuffles_within_the_boards_that_have_a_camera():
    firsts = {choose(MIXED, seed=s)[0].port for s in range(40)}
    assert firsts == {11, 13, 15}


def test_naming_a_camera_less_board_picks_it():
    (only,) = choose(MIXED, seed=1, wanted={"pi-sw2-p10"})
    assert only.hostname == "pi-sw2-p10" and only.has_camera is False


def test_naming_boards_keeps_the_camera_first_order_among_them():
    named = {"pi-sw2-p10", "pi-sw2-p13"}
    assert [b.hostname for b in choose(MIXED, seed=3, wanted=named)] == ["pi-sw2-p13", "pi-sw2-p10"]


def test_a_camera_less_board_is_tried_when_it_is_all_there_is():
    assert [b.port for b in choose([_cam("a", 1, False)], seed=1)] == [1]


def test_why_picked_says_the_board_the_reason_the_seed_and_the_camera_count():
    assert why_picked(MIXED[1], MIXED, 42) == (
        "picked pi-sw2-p11: has a camera; seed 42; 3 of 6 boards have a camera"
    )


def test_why_picked_says_when_a_camera_less_board_was_the_last_resort_or_was_named():
    assert "has no camera, tried after the boards that have one" in why_picked(MIXED[0], MIXED, 1)
    assert "named by --boards; has no camera" in why_picked(MIXED[0], MIXED, 1, {"pi-sw2-p10"})


def test_why_picked_does_not_claim_a_camera_the_site_has_not_said():
    assert "does not say whether it has a camera" in why_picked(MIXED[2], MIXED, 1)
