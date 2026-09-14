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
    """The page that opened is the board's page, and it says what hardware it is.

    A person choosing a board needs both: welland's heading reads "Accessing
    pi-sw2-p37 -- Digilent Arty A7-35T"; a heading that stops at the hostname
    leaves them to guess what they are about to program.
    """
    board = session.board
    heading = session.page.locator("h1").first.inner_text(timeout=10_000)
    evidence.claim(
        f"the page heading names {board.hostname}",
        board.hostname in heading,
        detail=f"heading reads {heading!r}",
    )
    after_name = heading.split(board.hostname, 1)[-1].strip(" -\u2014\u2013:") if board.hostname in heading else ""
    evidence.claim(
        "the page says what FPGA board is fitted",
        bool(after_name) or bool(board.fpga_board),
        detail=f"heading reads {heading!r}; the index said {board.fpga_board!r}",
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
    # the WebSocket bytes, the clipboard copy, and OCR of the pixels. The
    # name must be a line of its own in the output: tmux's status line also
    # carries the hostname, and a repaint of it is not `hostname` answering.
    hostname = terminal.run("hostname")
    shown, detail = hostname.shows(board.hostname)
    evidence.ground_truth(
        "the web terminal reaches the board the page says it is",
        shown and board.hostname in hostname.lines(),
        detail=f"{detail}; output lines {hostname.lines()!r}",
    )

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
    # Only what the click added counts: an old line from before the click is
    # not an answer to it.
    state = status.poe_state(since=baseline)
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

    # The reasoning a person does: it cannot have been up for longer than the
    # time since I pressed the button. That is the whole test; "uptime went
    # backwards" is not, because a board that was rebooted ten minutes ago
    # and is rebooted again now has a larger uptime after than before, and
    # a fixed ceiling fails a slow but perfectly good power cycle.
    elapsed = time.monotonic() - clicked_at
    evidence.ground_truth(
        "the Pi booted after the button was pressed",
        after <= elapsed + 30,
        detail=f"uptime {after:.1f}s (was {before:.1f}s), {elapsed:.1f}s since the click",
    )


# -- bitstream upload ---------------------------------------------------------

BITSTREAM = Path(__file__).parents[1] / "fixtures" / "counter_test" / "top.bit"
# Where the page's own scp instructions put files ("...:Uploads"), spelled out
# because the shared tmux session is not necessarily at $HOME: the page's
# "Blink LEDs" button leaves it in ~/Demos/counter_test.
REMOTE = "~/Uploads/top.bit"

# Fractions of the picture (below the clock overlay) whose pixels have to move
# for the board to count as changed, and as still running. Calibrated on ps1
# pi7 on 2026-09-14 with the page's own "Blink LEDs" button, which loads this
# same counter design: with the LEDs still, shots two seconds apart differed
# in 0.0000% of pixels (one blip of 0.0006%); once the counter was running,
# consecutive shots differed by 0.03% to 3%, though about one pair in ten
# was identical, which is why keeps_changing looks at several pairs. The
# change reached the picture about 40s after the click. A later pass on pi9
# saw a genuine pair at 0.018%, so the line is drawn nearer the noise: eight
# times the largest blip seen, a quarter of the smallest real change.
CHANGED = 0.00005
STILL_RUNNING = 0.00005


_ERROR_PAGE = ("traceback", "server error", "exception", "not found", "forbidden")


def upload_succeeded(page_text: str) -> bool:
    """Does the page the form landed on report the upload, and nothing gone wrong?"""
    text = page_text.lower()
    return "uploaded" in text and not any(word in text for word in _ERROR_PAGE)


def file_is_fresh(text: str, window: int = 600) -> tuple[bool, str]:
    """Was the file written within `window` seconds, by the Pi's own clock?

    `text` is what `date +%s; stat -c %Y FILE` printed: the Pi's clock, then
    the file's mtime, both epoch seconds from the same clock. Comparing the
    mtime against this machine's clock instead would make the answer depend
    on two clocks agreeing, which nothing here checks.
    """
    stamps = re.findall(r"^\s*(\d{9,11})\s*$", text, re.MULTILINE)
    if len(stamps) < 2:
        return False, f"could not read the Pi's clock and the file's mtime from {text!r}"
    now, mtime = int(stamps[-2]), int(stamps[-1])
    age = now - mtime
    return 0 <= age <= window, f"the file is {age}s old by the Pi's own clock (now {now}, mtime {mtime})"


def upload_programs_the_board(session: BoardSession, evidence: EvidenceLog) -> None:
    """Can a person upload a bitstream through the form and see it running?

    The claim is the success page. The ground truth is that the file really
    landed on the Pi at the right size and just now, that openFPGALoader
    really programmed the part, and that the LEDs visibly changed and are
    moving.

    Known limitation: counter_test/top.bit is the same bitstream the "Blink
    LEDs" button loads, so the camera proves "the LEDs changed and are
    counting" but not "this upload is what is running".
    """
    page, terminal, camera = session.page, session.terminal, session.camera

    live, detail = camera.check_live_with_recovery(timeout=60)
    evidence.ground_truth("the camera is live before the upload", live, detail=detail)
    before = camera.shot()

    page.set_input_files("#upform input[type=file]", str(BITSTREAM))
    page.click("#upform input[type=submit]")
    try:
        page.wait_for_load_state("domcontentloaded")
        # Read the rendered text, not the HTML source. The site runs with
        # DEBUG=True, so a failed upload renders Django's technical traceback,
        # whose visible text contains both "handle_uploaded_file" and the
        # request URL with pino= in it. Only a page that reports the upload
        # and is not an error page counts.
        landed = page.inner_text("body")
        evidence.claim(
            "the upload form reports success, not an error page",
            upload_succeeded(landed),
            detail=f"landed on {page.url} showing: {landed[:400]!r}",
        )
    finally:
        # Whatever the form did, come back to the board page: everything after
        # this, and every journey after this one, reads it.
        page.go_back()
    terminal.reset()
    try:
        terminal.wait_for_prompt(timeout=45)
    except TimeoutError as exc:
        evidence.ground_truth("the web terminal is back after returning to the page", False, detail=str(exc))

    # The size alone does not prove THIS upload landed: the identical file
    # from a previous run, or another user's, satisfies it just as well. A
    # person checks the file is new, so ask when it was written too.
    listing = terminal.run(f"ls -l {REMOTE}")
    shown, detail = listing.shows(str(BITSTREAM.stat().st_size))
    evidence.ground_truth("the bitstream really landed on the Pi at the right size", shown, detail=detail)

    stamped = terminal.run(f"date +%s; stat -c %Y {REMOTE}")
    fresh, detail = file_is_fresh(stamped.text)
    if fresh:
        # The numbers came off the WebSocket; the mtime has to be on screen too.
        fresh, shown = stamped.shows(detail.rsplit("mtime ", 1)[-1].rstrip(")"))
        detail = f"{detail}; {shown}"
    evidence.ground_truth("the file on the Pi was written just now, not left over from before", fresh, detail=detail)

    programming = terminal.run(f"openFPGALoader -b arty {REMOTE}", timeout=180)
    status, detail = terminal.exit_status()
    evidence.ground_truth(
        "openFPGALoader programmed the FPGA",
        status == 0,
        detail=f"exit status {status} ({detail}); output: {programming.text[-400:]!r}",
    )

    # The feed runs about a minute behind, so keep watching rather than
    # comparing one shot taken the moment programming finished.
    changed, detail = camera.wait_for_change(before, threshold=CHANGED, timeout=120)
    evidence.ground_truth("the board looks different from before the upload", changed, detail=detail)

    counting, detail = camera.keeps_changing(threshold=STILL_RUNNING)
    evidence.ground_truth("the design is visibly running, not frozen", counting, detail=detail)
