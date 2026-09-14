"""Following the page's "use your own ssh client" instructions, literally.

The board page prints `ssh -p 23722 pi@welland.fpgas.online` in a
click-to-copy block. A person pastes that into a terminal, answers the
first-connection host-key question, reads the password out of the login
banner, types it, and gets a shell. This module does exactly that with the
real OpenSSH client in a pseudo-terminal, and reads what it prints the way a
person reads it. Nothing here reconstructs the connection from the prose
around the command: if the printed command is wrong, this fails.
"""

from __future__ import annotations

import dataclasses
import re
import shlex
import time
from pathlib import Path

import pexpect

from e2e import ocr
from e2e.sshbanner import password_from_banner
from e2e.terminal import DEFAULT_PROMPT, at_a_prompt, strip_prompt_and_echo

_HOST_KEY_QUESTION = r"\(yes/no(?:/\[fingerprint\])?\)\?"
_PASSWORD_PROMPT = r"[Pp]assword:"
# What the page's block must look like for this to be the page's command and
# not ours: the ssh client, a port, and user@host. Anything else is refused.
_PRINTED_COMMAND = re.compile(r"^ssh\s+-p\s*\d+\s+\S+@[\w.-]+$")


# The page addresses a visitor who has no key on the board. The machine running
# this may well have one -- the fleet's own maintainers do -- and OpenSSH would
# use it silently, logging in with no password prompt and proving nothing about
# the instructions. So: no keys, no agent, the password the banner gives.
VISITOR_OPTIONS = ["-o", "PubkeyAuthentication=no", "-o", "IdentityAgent=none"]


class SshFailed(RuntimeError):
    """The login did not reach a shell. The message quotes what ssh printed."""


@dataclasses.dataclass(frozen=True)
class SshLogin:
    command: str
    banner: str
    password: str
    outputs: dict[str, str]
    transcript: str


def printed_command_argv(command: str) -> list[str]:
    """The argv for the command exactly as the page prints it."""
    command = command.strip()
    if not _PRINTED_COMMAND.match(command):
        raise ValueError(f"not an ssh command a page would print: {command!r}")
    return shlex.split(command)


def banner_from(printed: str) -> str:
    """The login banner, out of everything ssh printed before asking for a password.

    That output also holds the host-key question and our "yes", the client's
    "Permanently added" note, and the password prompt itself. None of those
    is the banner, which is what the *server* said.
    """
    text = re.sub(
        r"The authenticity of host.*?" + _HOST_KEY_QUESTION + r"\s*(?:yes)?", "", printed, flags=re.DOTALL
    )
    text = re.sub(r"Warning: Permanently added[^\n]*\n?", "", text)
    text = re.sub(r"\S+@[\w.-]+'s\s+" + _PASSWORD_PROMPT + r".*$", "", text, flags=re.DOTALL)
    return "\n".join(line.strip() for line in text.splitlines() if line.strip())


def _read_until(child, done, timeout: float, quiet: float = 1.0) -> str:
    """Read from the pty until `done(text)` holds and the output has settled.

    tmux repaints its status line constantly, so "no more output" never quite
    arrives; settling on the *predicate* holding across a quiet interval is
    what a person does when they see the prompt sit still.
    """
    deadline = time.monotonic() + timeout
    text = ""
    satisfied_since = None
    while time.monotonic() < deadline:
        try:
            text += child.read_nonblocking(size=4096, timeout=0.5)
        except pexpect.TIMEOUT:
            pass
        except pexpect.EOF:
            break
        if done(ocr.strip_ansi(text)):
            satisfied_since = satisfied_since or time.monotonic()
            if time.monotonic() - satisfied_since >= quiet:
                return text
        else:
            satisfied_since = None
    return text


def _after(child) -> str:
    return child.after if isinstance(child.after, str) else ""


def log_in_with_the_printed_command(
    command: str,
    commands: list[str],
    known_hosts: Path,
    timeout: float = 30.0,
    prompt: str = DEFAULT_PROMPT,
) -> SshLogin:
    """Run the page's ssh command, log in with the banner's password, run `commands`.

    `known_hosts` is a file for this run, so every run meets the host for the
    first time and has to answer the "continue connecting?" question -- which
    is what a new user sees. It is the one addition to the printed command.
    """
    argv = printed_command_argv(command)
    argv[1:1] = VISITOR_OPTIONS + ["-o", f"UserKnownHostsFile={known_hosts}"]
    known_hosts.parent.mkdir(parents=True, exist_ok=True)
    child = pexpect.spawn(argv[0], argv[1:], encoding="utf-8", timeout=timeout, dimensions=(40, 120))
    transcript = ""
    try:
        # A person first sees either the host-key question or the banner and
        # then the password prompt.
        which = child.expect([_HOST_KEY_QUESTION, _PASSWORD_PROMPT, pexpect.EOF, pexpect.TIMEOUT])
        transcript += child.before + _after(child)
        if which == 0:
            child.sendline("yes")
            which = child.expect([_PASSWORD_PROMPT, pexpect.EOF, pexpect.TIMEOUT]) + 1
            transcript += child.before + _after(child)
        printed = ocr.normalise(transcript)
        if which == 3:
            raise SshFailed(f"{command!r} printed nothing more within {timeout}s; so far: {printed!r}")
        if which == 2:
            raise SshFailed(f"{command!r} exited before asking for a password; it printed {printed!r}")

        banner = banner_from(transcript)
        password = password_from_banner(banner)
        if password is None:
            raise SshFailed(f"the login banner does not contain a password; it read {banner!r}")
        child.sendline(password)

        text = _read_until(child, lambda t: at_a_prompt(t, prompt), timeout)
        transcript += text
        if not at_a_prompt(ocr.strip_ansi(text), prompt):
            raise SshFailed(f"no shell prompt after typing the banner's password; saw {ocr.normalise(text)!r}")

        outputs: dict[str, str] = {}
        for cmd in commands:
            child.sendline(cmd)
            text = _read_until(child, lambda t, c=cmd: c in t and at_a_prompt(t.split(c, 1)[-1], prompt), timeout)
            transcript += text
            after_echo = ocr.strip_ansi(text).split(cmd, 1)[-1]
            outputs[cmd] = strip_prompt_and_echo(after_echo, cmd, prompt)
        return SshLogin(command=command, banner=banner, password=password, outputs=outputs, transcript=transcript)
    finally:
        # Just hang up. The shell on the other end is a shared tmux session;
        # typing `exit` into it would end everyone's shell, and a person who
        # is done simply closes their terminal.
        child.close(force=True)
