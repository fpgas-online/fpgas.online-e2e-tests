"""The status log box on a board page.

The textarea under the video, which the page fills with the Pi's own reports
and the SNMP results. It is rendered on screen, so a test may assert on it --
but it is the site talking about itself, so it is never enough on its own.
Everything here produces claims.
"""

from __future__ import annotations

import time


class StatusLog:
    def __init__(self, page, port: int):
        self.page = page
        self.selector = f"#log{port}"

    def text(self) -> str:
        return self.page.locator(self.selector).input_value()

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
