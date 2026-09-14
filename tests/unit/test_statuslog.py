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


# What ps1 pi7's box read on 2026-09-14 after Reset, verbatim.
AFTER_RESET = (
    "00:33:12: socket closed.\n00:33:12: socket connected\n00:33:12: snmp: set power off\n"
    "00:33:12: checking status: 7\n00:33:12: snmp: get power off\n00:33:13: snmp: set power on\n"
)


def test_the_poe_state_is_the_last_word_the_box_used():
    assert _box(AFTER_RESET).poe_state() == "on"


def test_the_poe_state_reads_off_after_a_get():
    assert _box("00:33:12: snmp: get power off\n").poe_state() == "off"


def test_a_box_that_never_mentioned_power_has_no_state():
    """welland: the status endpoint 500s, so the box only ever says 'checking status'."""
    box = _box("00:34:05: socket connected\n00:34:05: checking status: 37\n00:34:11: socket closed.\n")
    assert box.poe_state() == ""
