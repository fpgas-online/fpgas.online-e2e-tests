"""What a person does on a board page, as procedures that record evidence.

Each journey takes an open BoardSession and an EvidenceLog and does one thing
a user does -- watch the camera, use the terminal, follow the ssh
instructions, press Reset -- recording what it saw. The one-board tests in
tests/shared and the whole-site audit both call these, so the audit measures
exactly what the tests measure and nothing else.

A journey stops at the first ground-truth failure (the log raises), and
carries on past a failed claim so that it still gets to look at reality.
"""

from __future__ import annotations

import re
import time
from pathlib import Path

from e2e.evidence import EvidenceLog
from e2e.session import BoardSession
from e2e.sshbanner import parse_instructions
from e2e.sshclient import SshFailed, log_in_with_the_printed_command

# /proc/uptime is exactly two floats on one line: seconds up, seconds idle.
# Anchored, because an unanchored number picks up the clock in the prompt
# ("06:25:33 pi@pi2:~ $" yields 33) and a plausible-looking wrong answer is
# worse than no answer.
UPTIME = re.compile(r"^\s*(\d+\.\d+)\s+\d+\.\d+\s*$", re.MULTILINE)

# What the board page says about itself while it reboots: the kernel "can take
# up to 2 minutes", and the video feed runs about 60s behind. The waits below
# come from those numbers rather than from guesses.
BOOT_BUDGET = 300.0


def page_names_the_board(session: BoardSession, evidence: EvidenceLog) -> None:
    """The page that opened is the board's page: its heading says so."""
    board = session.board
    heading = session.page.locator("h1").first.inner_text(timeout=10_000)
    evidence.claim(
        f"the page heading names {board.hostname}",
        board.hostname in heading,
        detail=f"heading reads {heading!r}",
    )


def camera_is_live(session: BoardSession, evidence: EvidenceLog, timeout: float = 60.0) -> None:
    """A live picture, using the page's own "reset video player" button if needed.

    Recovering, not just waiting: a stuck player never starts however long
    you wait, and calls a healthy camera dead about a quarter of the time.
    """
    board, camera = session.board, session.camera
    live, detail = camera.check_live_with_recovery(timeout=timeout)
    evidence.ground_truth(
        f"{board.hostname}'s camera is showing a live picture",
        live,
        # player_state() is DOM internals, which no user sees. It belongs in
        # the detail of a failure, not in the record of what proved a pass.
        detail=detail if live else f"{detail}; player {camera.player_state()}",
    )


def terminal_reaches_the_board(session: BoardSession, evidence: EvidenceLog, timeout: float = 45.0) -> None:
    """The web terminal gives a prompt on the board the page says it is."""
    board, terminal = session.board, session.terminal
    try:
        terminal.wait_for_prompt(timeout=timeout)
    except TimeoutError as exc:
        evidence.ground_truth("the web terminal reaches a shell prompt", False, detail=str(exc))

    # The terminal is a canvas, so this also proves all three readings agree:
    # the WebSocket bytes, the clipboard copy, and OCR of the pixels.
    hostname = terminal.run("hostname")
    shown, detail = hostname.shows(board.hostname)
    evidence.ground_truth("the web terminal reaches the board the page says it is", shown, detail=detail)

    uptime = terminal.run("uptime -p")
    shown, detail = uptime.shows("up")
    evidence.ground_truth("the Pi answers a second command", shown, detail=detail)


def poe_status_is_reported(session: BoardSession, evidence: EvidenceLog, timeout: float = 30.0) -> str:
    """Press "Check PoE" and read what the status box says. Returns "on", "off" or "".

    The box is the site talking about itself, so this is a claim. The one
    cross-check available to a person is the picture: a camera that is
    streaming is running on a Pi that has power, so a box that says "off"
    under a live picture is wrong.
    """
    board, status, page = session.board, session.status, session.page
    baseline = status.text()
    page.click(f"#status{board.port}")
    seen, detail = status.wait_for_new("power", baseline, timeout=timeout)
    evidence.claim("the status box reports the PoE state after 'Check PoE'", seen, detail=detail)
    state = status.poe_state()
    if state == "off":
        live, picture = session.camera.check_live(timeout=15)
        evidence.claim(
            "the status box does not say 'off' under a live picture",
            not live,
            detail=f"the box says power off; {picture}",
        )
    return state


def direct_ssh_works(session: BoardSession, evidence: EvidenceLog, known_hosts: Path, timeout: float = 30.0) -> None:
    """The ssh command the page prints, run in a real ssh client, reaches the board."""
    board, page = session.board, session.page
    instructions = parse_instructions(page.inner_text("body"))
    evidence.claim(
        "the page prints an ssh command to copy",
        bool(instructions.ssh_command),
        detail=f"page says: {instructions}",
    )
    command = instructions.ssh_command
    try:
        login = log_in_with_the_printed_command(command, ["hostname"], known_hosts, timeout=timeout)
    except (SshFailed, ValueError) as exc:
        evidence.ground_truth(f"`{command}` logs in with the banner's password", False, detail=str(exc))
        return
    evidence.ground_truth(
        f"`{command}` logs in with the banner's password", True, detail=f"the banner read {login.banner!r}"
    )
    remote = login.outputs["hostname"]
    evidence.ground_truth(
        "ssh reached the board the page said it would",
        board.hostname in remote.split(),
        detail=f"page said {board.hostname!r}, `hostname` over ssh printed {remote!r}",
    )


def _uptime_seconds(terminal, evidence: EvidenceLog, when: str) -> float:
    out = terminal.run("cat /proc/uptime")
    match = UPTIME.search(out.text)
    evidence.ground_truth(
        f"the Pi reported its uptime {when}",
        match is not None,
        detail=f"terminal showed {out.text!r}",
    )
    seconds = float(match.group(1))
    # Cross-check the number itself on the screen, not a full stop that any
    # prompt would satisfy.
    shown, detail = out.shows(match.group(1))
    evidence.ground_truth(f"the uptime is legible on screen {when}", shown, detail=detail)
    return seconds


def reset_power_cycles_the_board(session: BoardSession, evidence: EvidenceLog) -> None:
    """Does "turn it off and on again" actually turn the board off and on again?

    The claim is the status box. The ground truth is that the camera stops
    seeing a live picture -- the camera runs on the Pi, so the feed dying IS
    the Pi dying -- and that the Pi's own uptime went backwards afterwards.
    """
    board, page, camera, status, terminal = (
        session.board,
        session.page,
        session.camera,
        session.status,
        session.terminal,
    )
    name = board.hostname

    live, detail = camera.check_live(timeout=60)
    evidence.ground_truth(f"{name}'s camera feed is live before the reset", live, detail=detail)

    try:
        terminal.wait_for_prompt(timeout=45)
    except TimeoutError as exc:
        evidence.ground_truth("the web terminal works before the reset, so uptime can be read", False, detail=str(exc))
    before = _uptime_seconds(terminal, evidence, "before the reset")

    # Everything the box says from here on is a consequence of the click. The
    # box accumulates and the click itself makes the page re-ask for the PoE
    # state, so without this baseline the status assertion matches text the
    # click produced whether or not the port was ever switched.
    baseline = status.text()
    clicked_at = time.monotonic()
    page.click(f"#reset{board.port}")

    seen, detail = status.wait_for_new("set power", baseline, timeout=30)
    evidence.claim("the status box reports the PoE port being switched", seen, detail=detail)

    stopped, detail = camera.check_stopped(timeout=120)
    evidence.ground_truth(f"{name} stopped sending video, so it really lost power", stopped, detail=detail)

    returned, detail = camera.check_live_with_recovery(timeout=BOOT_BUDGET)
    evidence.ground_truth(f"{name}'s camera feed came back", returned, detail=detail)

    # Wait for the page to say ssh is back before trying to use it. The Pi has
    # only just rebooted, so clicking "reset ssh" first gets an authentication
    # failure and no terminal is ever built -- which is what a person would
    # see too, and why the page announces this.
    seen, detail = status.wait_for_new("ssh server started.", baseline, timeout=180)
    evidence.claim("the status box reports the Pi's ssh server coming back", seen, detail=detail)

    # Not just "did it come back" but "did it stay up": right after a reboot
    # the channel can close moments after connecting.
    terminal.wait_until_usable(timeout=300)
    after = _uptime_seconds(terminal, evidence, "after the reset")

    evidence.ground_truth(
        "the Pi's uptime went backwards, so it really rebooted",
        after < before,
        detail=f"before={before:.1f}s after={after:.1f}s",
    )
    # The reasoning a person does: it cannot have been up for longer than the
    # time since I pressed the button. A fixed ceiling instead fails a slow
    # but perfectly good power cycle, because the waits above can legitimately
    # take several minutes.
    elapsed = time.monotonic() - clicked_at
    evidence.ground_truth(
        "the Pi booted since the button was pressed",
        after <= elapsed + 30,
        detail=f"uptime {after:.1f}s, {elapsed:.1f}s since the click",
    )
