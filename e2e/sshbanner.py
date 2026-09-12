"""The 'use your own ssh client' instructions, and the banner they point at.

The board page tells the user a host, a port and that the password is in the
login banner. This module reads those instructions the way a person reads them
and then follows them.
"""

from __future__ import annotations

import dataclasses
import re
import socket

import paramiko

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


def read_version_string(host: str, port: int, timeout: float = 15.0) -> str:
    """The "SSH-2.0-..." identification string the server sends on connect.

    Proves the advertised port is answering ssh at all. This is NOT the login
    banner -- see read_login_banner.
    """
    with socket.create_connection((host, port), timeout=timeout) as sock:
        sock.settimeout(timeout)
        try:
            return sock.recv(512).decode("utf-8", "replace")
        except (TimeoutError, OSError):
            return ""


def read_login_banner(host: str, port: int, username: str = "pi", timeout: float = 20.0) -> str:
    """The banner a real ssh client prints before prompting for a password.

    OpenSSH sends this as SSH_MSG_USERAUTH_BANNER *during* authentication, so
    reading the raw socket only ever gets the version string. A client sees it
    after key exchange, when it first tries to authenticate -- which is what
    this does, with the "none" method that every server rejects.
    """
    transport = paramiko.Transport((host, port))
    try:
        transport.start_client(timeout=timeout)
        try:
            transport.auth_none(username)
        except paramiko.SSHException:
            pass  # expected: the point is the banner the attempt elicits
        banner = transport.get_banner()
    finally:
        transport.close()
    if banner is None:
        return ""
    return banner.decode("utf-8", "replace") if isinstance(banner, bytes) else banner


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
