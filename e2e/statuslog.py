"""The status log box on a board page.

The textarea under the video, which the page fills with the Pi's own reports
and the SNMP results. It is rendered on screen, so a test may assert on it --
but it is the site talking about itself, so it is never enough on its own.
Everything here produces claims.
"""

from __future__ import annotations

import re
import time

# What the page writes (fpgas.online-site pistat static/dcws.js, show_poe_result):
# "<time>: <what>: PoE <state>" with <what> "status" after "Check PoE" and
# "reset" after Reset; after Reset the state is "<a> then <b>". The status
# request is announced first as "checking status: <port>", which says nothing
# about the state, and a failure is "<what> failed (<code>): <error>", which is
# never a state. The box also carries other lines (websocket messages from the
# Pi, kernel and dnsmasq text), so only the site's own line shape counts: the
# whole line must end with the state. The time prefix is not matched (it is
# toLocaleTimeString, so "22:33:11" or "10:33:11 PM"), only the space before
# the word.
_POE_REPORT = re.compile(
    r"(?:^|\s)(?:status|reset): PoE ((?:on|off)(?: then (?:on|off))*)[ \t\r]*$", re.IGNORECASE | re.MULTILINE
)
# What a click on Reset adds to the box when the port was switched.
RESET_REPORT = re.compile(r"(?:^|\s)reset: PoE (?:on|off) then (?:on|off)[ \t\r]*$", re.IGNORECASE | re.MULTILINE)


class StatusLog:
    def __init__(self, page, port: int):
        self.page = page
        self.selector = f"#log{port}"

    def text(self) -> str:
        return self.page.locator(self.selector).input_value()

    def wait_for_new(self, needle: str, baseline: str, timeout: float = 60.0) -> tuple[bool, str]:
        """Wait for a line that was not already there.

        The box accumulates, and some lines are re-emitted by the very act of
        clicking: the Reset button closes and reopens the socket, which makes
        the page ask for the PoE state again. Searching the whole box for
        "power" therefore matches text the click itself produced, whether or
        not the port was ever switched. Only new text can be evidence that
        something happened.
        """
        deadline = time.monotonic() + timeout
        added = ""
        while time.monotonic() < deadline:
            current = self.text()
            added = current[len(baseline):] if current.startswith(baseline) else current
            if needle.lower() in added.lower():
                return True, f"after the click the box said: {added.strip()!r}"
            self.page.wait_for_timeout(500)
        return False, f"{needle!r} never appeared after the click; the box added: {added.strip()!r}"

    def wait_for_reset_report(self, baseline: str, timeout: float = 30.0) -> tuple[bool, str]:
        """Wait for "reset: PoE <a> then <b>" to be added after `baseline`: the port was switched."""
        deadline = time.monotonic() + timeout
        added = ""
        while True:
            current = self.text()
            added = current[len(baseline) :] if current.startswith(baseline) else current
            if RESET_REPORT.search(added):
                return True, f"after the click the box said: {added.strip()!r}"
            if time.monotonic() >= deadline:
                return False, f"no 'reset: PoE ... then ...' appeared after the click; the box added: {added.strip()!r}"
            self.page.wait_for_timeout(500)

    def wait_for_poe_state(self, baseline: str, timeout: float = 30.0) -> tuple[str, str]:
        """Wait for the box to report a PoE state that the click added.

        The click writes "checking status: <port>" itself, but so does the
        page when its socket opens, and that line cannot be told from the
        click's, so a load-time answer landing after the baseline is not
        excluded here; a refused or late answer still cannot pass, because
        only a "status: PoE on/off" line counts.

        Returns (state, detail): "on" or "off", or "" with the reason when
        nothing that reads as a report arrived (an error line such as
        "status failed (500): ..." is not one). Only new text counts.
        """
        deadline = time.monotonic() + timeout
        added = ""
        while True:  # read at least once, even with no time to wait
            current = self.text()
            added = current[len(baseline) :] if current.startswith(baseline) else current
            state = self.poe_state(since=baseline)
            if state:
                return state, f"after the click the box said: {added.strip()!r}"
            if time.monotonic() >= deadline:
                break
            self.page.wait_for_timeout(500)
        return "", f"no 'PoE on' or 'PoE off' appeared after the click; the box added: {added.strip()!r}"

    def poe_state(self, since: str = "") -> str:
        """The last PoE state the box reported: "on", "off", or "" if it never said.

        The box words it "status: PoE on" after "Check PoE" and "reset: PoE
        off then on" after a reset; the last word of the last such line is
        what a person reads off it. With `since` -- the box's text before
        a click -- only lines the click added are read, so a stale line from
        earlier is not mistaken for an answer.
        """
        current = self.text()
        added = current[len(since) :] if since and current.startswith(since) else current
        reports = _POE_REPORT.findall(added)
        return reports[-1].split()[-1].lower() if reports else ""

    def wait_for(self, needle: str, timeout: float = 60.0) -> tuple[bool, str]:
        """Wait for a line to appear. Returns (seen, detail) rather than raising."""
        deadline = time.monotonic() + timeout
        seen = ""
        while time.monotonic() < deadline:
            seen = self.text()
            if needle in seen:
                return True, f"{needle!r} appeared in the status box"
            self.page.wait_for_timeout(500)
        tail = "\n".join(seen.splitlines()[-8:])
        return False, f"{needle!r} never appeared within {timeout}s; box ended:\n{tail}"
