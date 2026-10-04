"""The 'use your own ssh client' instructions, and the password in the banner.

The board page tells the user a host, a port and that the password is in the
login banner. This module reads those instructions off the page the way a
person reads them; e2e.sshclient then follows them with a real ssh client.
"""

from __future__ import annotations

import dataclasses
import re

_DETAILS = re.compile(
    r"user:\s*(?P<user>\S+?),\s*host:\s*(?P<host>[\w.-]+),\s*port\s*(?P<port>\d+)",
    re.IGNORECASE,
)
_SSH_COMMAND = re.compile(r"ssh\s+-p\s*\d+\s+\S+@[\w.-]+")
# A credential printed on a line of its own: one token, no spaces, not prose.
_BARE_PASSWORD = re.compile(r"[\w.@:+/=-]{6,64}")
_PASSWORD = re.compile(
    r"password(?:\s+is|:)?\s*[\"']?(?P<pw>[^\"'\r\n]+?)[\"']?\s*$",
    re.IGNORECASE | re.MULTILINE,
)


@dataclasses.dataclass(frozen=True)
class SshInstructions:
    user: str
    host: str
    port: int
    ssh_command: str


def parse_instructions(page_text: str) -> SshInstructions:
    match = _DETAILS.search(page_text)
    if match is None:
        raise ValueError("the page does not state a user, host and port for direct ssh")
    command = _SSH_COMMAND.search(page_text)
    return SshInstructions(
        user=match.group("user"),
        host=match.group("host"),
        port=int(match.group("port")),
        ssh_command=command.group(0) if command else "",
    )


def password_from_banner(banner: str) -> str | None:
    """Pull the password out of a login banner.

    Two shapes are accepted. Some servers spell it out ("the password is X");
    the fpgas.online Pis just print the password on a line by itself, which is
    why a lone short token counts. A line of several words is prose, not a
    credential.
    """
    match = _PASSWORD.search(banner)
    if match:
        return match.group("pw").strip()

    lines = [line.strip() for line in banner.splitlines() if line.strip()]
    if len(lines) == 1 and _BARE_PASSWORD.fullmatch(lines[0]):
        return lines[0]
    return None
