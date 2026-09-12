"""The 'use your own ssh client' instructions, and the banner they point at.

The board page tells the user a host, a port and that the password is in the
login banner. This module reads those instructions the way a person reads them
and then follows them.
"""

from __future__ import annotations

import dataclasses
import re
import socket

_DETAILS = re.compile(
    r"user:\s*(?P<user>\S+?),\s*host:\s*(?P<host>[\w.-]+),\s*port\s*(?P<port>\d+)",
    re.IGNORECASE,
)
_SSH_COMMAND = re.compile(r"ssh\s+-p\s*\d+\s+\S+@[\w.-]+")
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


def read_banner(host: str, port: int, timeout: float = 15.0) -> str:
    """Everything the server sends before authentication."""
    chunks: list[bytes] = []
    with socket.create_connection((host, port), timeout=timeout) as sock:
        sock.settimeout(timeout)
        try:
            while len(b"".join(chunks)) < 8192:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                chunks.append(chunk)
        except (TimeoutError, OSError):
            pass
    return b"".join(chunks).decode("utf-8", "replace")


def password_from_banner(banner: str) -> str | None:
    match = _PASSWORD.search(banner)
    return match.group("pw").strip() if match else None
