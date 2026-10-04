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


def test_only_lines_the_click_added_answer_it():
    before = "00:33:12: snmp: get power on\n"
    assert _box(before).poe_state(since=before) == ""
    assert _box(before + "00:33:20: snmp: get power off\n").poe_state(since=before) == "off"


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
