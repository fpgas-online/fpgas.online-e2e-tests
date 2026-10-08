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
from e2e.terminal import (
    DEFAULT_PROMPT,
    TerminalBusy,
    TerminalLost,
    WebTerminal,
    at_a_prompt,
    read_shell_line,
    strip_prompt_and_echo,
)

_HOST_KEY_QUESTION = r"\(yes/no(?:/\[fingerprint\])?\)\?"
_PASSWORD_PROMPT = r"[Pp]assword:"
# What the ssh client itself prints when it wants the password: "pi@host's password:". Waiting for the bare
# word would stop at a banner line such as "password: <the password>", before the real prompt, and the
# banner would be cut short there.
_SSH_PASSWORD_PROMPT = r"\S+@[\w.-]+'s\s+" + _PASSWORD_PROMPT
# What the page's block must look like for this to be the page's command and
# not ours: the ssh client, a port, and user@host. Anything else is refused.
_PRINTED_COMMAND = re.compile(r"^ssh(?:\s+-[46])?\s+-p\s*\d+\s+[\w.-]+@[\w.-]+$")


# The page addresses a visitor who has no key on the board. The machine running
# this may well have one -- the fleet's own maintainers do -- and OpenSSH would
# use it silently, logging in with no password prompt and proving nothing about
# the instructions. So: no keys, no agent, the password the banner gives.
VISITOR_OPTIONS = ["-o", "PubkeyAuthentication=no", "-o", "IdentityAgent=none"]


class SshFailed(RuntimeError):
    """The login did not reach a shell. The message quotes what ssh printed."""


class SshUnreachable(SshFailed):
    """The ssh port could not be reached at all: refused, timed out, no route, or silence with nothing received.

    Not name-resolution failures, not a refused password, and nothing that
    happened after the server sent any output: those mean the port was reached.
    """


class SshNoBannerPassword(SshFailed):
    """The port answered and asked for a password, but the banner it showed holds no password.

    Only that: the server was reached and reached its password prompt. Not a
    refused password, not a closed connection, not a missing shell prompt.
    """


# ssh's own wording when the TCP connection to the port fails.
_UNREACHABLE = re.compile(
    r"connect to host \S+ port \d+: "
    r"(?:Connection refused|Connection timed out|Operation timed out|No route to host|Network is unreachable)"
)


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
    text = re.sub(_SSH_PASSWORD_PROMPT + r".*$", "", text, flags=re.DOTALL)
    return "\n".join(line.strip() for line in text.splitlines() if line.strip())


def refuse_if_line_busy(login_text: str) -> None:
    """Send nothing unless the shell's line is free: TerminalBusy for a visitor, TerminalLost for a fault.

    The ssh login may attach to a tmux session other visitors share, so
    `sendline` would append to their half-typed command and press Enter on
    it. What tmux painted on attaching shows the line. No visible prompt
    line is left to the caller, which has already looked for a prompt.
    """
    line = read_shell_line(login_text)
    if line.state == "busy":
        raise TerminalBusy(WebTerminal.busy_reason(line.text, login_text))
    if line.state in ("broken", "unknown"):
        raise TerminalLost(
            f"nothing was sent: the shell's line is {line.state} ({line.text!r}); "
            f"the login painted {ocr.normalise(login_text)[-300:]!r}"
        )


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

    Two things are added to the printed command, both to make this machine
    look like a visitor's: VISITOR_OPTIONS (no keys), and `known_hosts` as a
    file for this run, so every run meets the host for the first time and
    has to answer the "continue connecting?" question, as a new user does.
    """
    argv = printed_command_argv(command)
    argv[1:1] = VISITOR_OPTIONS + ["-o", f"UserKnownHostsFile={known_hosts}"]
    known_hosts.parent.mkdir(parents=True, exist_ok=True)
    child = pexpect.spawn(argv[0], argv[1:], encoding="utf-8", timeout=timeout, dimensions=(40, 120))
    transcript = ""
    try:
        # A person first sees either the host-key question or the banner and
        # then the password prompt.
        which = child.expect([_HOST_KEY_QUESTION, _SSH_PASSWORD_PROMPT, pexpect.EOF, pexpect.TIMEOUT])
        transcript += child.before + _after(child)
        if which == 0:
            child.sendline("yes")
            which = child.expect([_SSH_PASSWORD_PROMPT, pexpect.EOF, pexpect.TIMEOUT]) + 1
            transcript += child.before + _after(child)
        printed = ocr.normalise(transcript)
        if which == 3:
            if not printed:
                raise SshUnreachable(f"{command!r} printed nothing at all within {timeout}s")
            raise SshFailed(f"{command!r} printed nothing more within {timeout}s; so far: {printed!r}")
        if which == 2:
            if _UNREACHABLE.search(printed):
                raise SshUnreachable(f"{command!r} could not reach the port; it printed {printed!r}")
            raise SshFailed(f"{command!r} exited before asking for a password; it printed {printed!r}")

        banner = banner_from(transcript)
        password = password_from_banner(banner)
        if password is None:
            raise SshNoBannerPassword(f"the login banner does not contain a password; it read {banner!r}")
        child.sendline(password)

        text = _read_until(child, lambda t: at_a_prompt(t, prompt), timeout)
        transcript += text
        # A prompt line with someone's text after it never matches at_a_prompt,
        # so this has to be told apart from "no shell" first: that is a visitor.
        refuse_if_line_busy(ocr.strip_ansi(text))
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
