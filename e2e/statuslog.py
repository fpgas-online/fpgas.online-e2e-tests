"""The status log box on a board page.

The textarea under the video, which the page fills with the Pi's own reports
and the SNMP results. It is rendered on screen, so a test may assert on it --
but it is the site talking about itself, so it is never enough on its own.
Everything here produces claims.
"""

from __future__ import annotations

import re
import time

_POWER_LINE = re.compile(r"power\s+(on|off)\b", re.IGNORECASE)


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

    def poe_state(self) -> str:
        """The last PoE state the box reported: "on", "off", or "" if it never said.

        The box words it "snmp: get power on" after "Check PoE" and "snmp:
        set power off" during a reset; the last word of the last such line
        is what a person reads off it.
        """
        states = _POWER_LINE.findall(self.text())
        return states[-1].lower() if states else ""

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
