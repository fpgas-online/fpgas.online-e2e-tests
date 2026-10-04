import inspect

import pytest

from e2e import journeys
from e2e.statuslog import StatusLog


class _Page:
    def __init__(self, text):
        self._text = text

    def locator(self, _selector):
        return self

    def input_value(self):
        return self._text


def _box(text):
    return StatusLog(_Page(text), 7)


# What a box reads after Reset, in the site's wording (dcws.js).
AFTER_RESET = (
    "00:33:12: socket closed.\n00:33:12: socket connected\n00:33:12: checking status: 7\n"
    "00:33:12: status: PoE off\n00:33:13: reset: PoE off then on\n"
)


def test_the_poe_state_is_the_last_word_the_box_used():
    assert _box(AFTER_RESET).poe_state() == "on"


def test_the_poe_state_reads_off_after_a_get():
    assert _box("00:33:12: status: PoE off\n").poe_state() == "off"


def test_a_box_that_never_mentioned_power_has_no_state():
    """welland: the status endpoint 500s, so the box only ever says 'checking status'."""
    box = _box("00:34:05: socket connected\n00:34:05: checking status: 37\n00:34:11: socket closed.\n")
    assert box.poe_state() == ""


def test_only_lines_the_click_added_answer_it():
    before = "00:33:12: status: PoE on\n"
    assert _box(before).poe_state(since=before) == ""
    assert _box(before + "00:33:20: status: PoE off\n").poe_state(since=before) == "off"


# What a board page's box read on 2026-10-04 after "Check PoE" on welland: the page announces the
# question, then writes the answer in the wording of fpgas.online-site pistat static/dcws.js.
SITE_STATUS = "22:33:10: socket connected\n22:33:10: checking status: 46\n22:33:11: status: PoE on\n"


def test_the_sites_current_status_wording_reads_as_on():
    assert _box(SITE_STATUS).poe_state() == "on"


def test_the_sites_current_status_wording_reads_as_off():
    assert _box("22:33:10: checking status: 46\n22:33:11: status: PoE off\n").poe_state() == "off"


def test_a_reset_report_reads_as_its_last_state():
    assert _box("22:33:11: reset: PoE off then on\n").poe_state() == "on"
    assert _box("22:33:11: reset: PoE on then off\n").poe_state() == "off"


def test_the_question_alone_and_an_error_are_not_a_state():
    """'checking status' only says it was asked; 'status failed' says it was not answered."""
    assert _box("22:33:10: checking status: 46\n").poe_state() == ""
    assert _box("22:33:10: checking status: 46\n22:33:11: status failed (500): no answer\n").poe_state() == ""


class _GrowingPage(_Page):
    """A box that gets its answer on the second look."""

    def __init__(self, texts):
        super().__init__(texts[0])
        self._texts = list(texts)

    def input_value(self):
        return self._texts.pop(0) if len(self._texts) > 1 else self._texts[0]

    def wait_for_timeout(self, _ms):
        pass


def test_waiting_for_the_state_returns_what_the_click_added():
    before = "22:30:00: socket connected\n"
    asked = before + "22:33:10: checking status: 46\n"
    page = _GrowingPage([before, asked, asked + "22:33:11: status: PoE on\n"])
    state, detail = StatusLog(page, 46).wait_for_poe_state(before, timeout=5)
    assert state == "on"
    assert "status: PoE on" in detail


def test_waiting_for_the_state_fails_loudly_when_only_the_question_appears():
    before = "22:30:00: socket connected\n"
    page = _GrowingPage([before + "22:33:10: checking status: 46\n"])
    state, detail = StatusLog(page, 46).wait_for_poe_state(before, timeout=0)
    assert state == ""
    assert "checking status: 46" in detail


@pytest.mark.parametrize(
    "line",
    [
        "status failed (500): switch says PoE off",
        "status failed (502): PoE on port unreachable",
        "status failed (404): power on",
        "kernel: usb 1-1: power off",
        "status: PoE on-line",
        "status: PoE on port 3",
        "snmp: get power on",  # the old wording is gone from the site
        "dnsmasq: reset: PoE-less lease",
    ],
)
def test_other_lines_in_the_box_are_never_a_state(line):
    assert _box(f"22:33:11: {line}\n").poe_state() == ""


def test_a_twelve_hour_time_prefix_does_not_hide_the_report():
    assert _box("10:33:11 PM: status: PoE off\n").poe_state() == "off"
    assert _box("10:33:11 PM: reset: PoE off then on").poe_state() == "on"


def test_the_reset_report_needs_both_states_and_only_counts_what_the_click_added():
    before = "22:30:00: reset: PoE off then on\n"
    page = _GrowingPage([before + "22:33:11: reset failed (500): x\n"])
    ok, _ = StatusLog(page, 46).wait_for_reset_report(before, timeout=0)
    assert not ok
    page = _GrowingPage([before + "22:33:11: reset: PoE off then on\n"])
    ok, detail = StatusLog(page, 46).wait_for_reset_report(before, timeout=0)
    assert ok and "reset: PoE off then on" in detail
    ok, _ = StatusLog(_GrowingPage([before]), 46).wait_for_reset_report(before, timeout=0)
    assert not ok


def test_the_reset_journey_waits_through_the_status_logs_reset_report():
    """Pins the journey to the site's wording by way of StatusLog, not a literal of its own."""
    source = inspect.getsource(journeys.reset_power_cycles_the_board)
    assert "wait_for_reset_report" in source
    assert "set power" not in source
