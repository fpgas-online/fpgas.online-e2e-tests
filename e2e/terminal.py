"""The web terminal the board page embeds, driven the way a person drives it.

The page embeds huashengdun/webssh in an iframe whose URL already carries the
credentials, so nothing here needs a password.

WebSSH bundles xterm.js 4.x with the default canvas renderer, so the terminal
text is NOT in the DOM and the xterm buffer API is locked inside a closure.
Output is therefore read three independent ways, and an assertion must hold in
all three:

  1. the WebSSH WebSocket frames -- exact, cheap, but transport rather than
     screen, so on its own only a claim about what is displayed;
  2. the clipboard, after selecting the terminal and copying, which is the
     gesture a person uses to grab terminal output;
  3. OCR of a screenshot, which is literally what is on the screen.

Input is always real keystrokes.
"""

from __future__ import annotations

import io
import re
import time

from PIL import Image

from e2e import ocr

# A shell prompt as it really appears: "06:25:33 pi@pi2:~/Demos/counter_test $ ".
# Deliberately NOT anchored to the end of the buffer. The board pages attach to
# a shared tmux session which redraws constantly, so the last thing in the
# buffer is almost always a redraw or a status line, never the prompt.
# The \r matters: lines arrive CRLF-terminated, so the trailing class has to
# absorb the carriage return before $ can match at the line end.
DEFAULT_PROMPT = r"[\w.-]+@[\w.-]+:[^\r\n]*?[$#][ \t\r]*$"
_WSSH_WS = "/wssh/ws"


def decode_wssh_frames(frames: list[bytes | str]) -> str:
    """Concatenate the terminal output WebSSH sends.

    The two directions are not symmetric. Client->server is JSON --
    `sock.send(JSON.stringify({'data': data}))` in WebSSH's main.js. But
    server->client is BINARY frames of raw terminal bytes, which its client
    hands straight to xterm via `read_file_as_text(msg.data, term_write,
    decoder)`. There is no JSON to unwrap on the way in.

    Decoding is lenient because a frame boundary can fall in the middle of a
    multi-byte character; losing one glyph beats raising mid-test.
    """
    return "".join(f.decode("utf-8", "replace") if isinstance(f, bytes) else f for f in frames)


# xterm draws the cursor as a filled block, which tesseract reads as "[]" (or
# a stray bracket) sitting immediately after the prompt. Captured from ps1
# pi7 on 2026-09-13: "07:38:03 pi@pi7:~ $ []". Left in place it defeats any
# end-of-line anchor, so the suite reports a terminal it can plainly see as
# dead.
_CURSOR = re.compile(r"[\[\]|_]+[ \t]*$", re.MULTILINE)


def without_cursor(text: str) -> str:
    """Drop the rendered cursor from the end of each line of OCR'd screen text."""
    return _CURSOR.sub("", text)


def at_a_prompt(text: str, prompt: str = DEFAULT_PROMPT) -> bool:
    """Has the shell printed a prompt anywhere in this output?

    Strips ANSI first: the prompt is wrapped in colour codes and followed by
    more escapes, so matching the raw bytes finds nothing.
    """
    return re.search(prompt, ocr.strip_ansi(text), re.MULTILINE) is not None


def strip_prompt_and_echo(text: str, command: str, prompt: str = DEFAULT_PROMPT) -> str:
    """Drop the echoed command and the prompt the shell printed afterwards."""
    body = ocr.strip_ansi(text)
    lines = [line.rstrip("\r") for line in body.split("\n")]
    if lines and command.strip() and command.strip() in lines[0]:
        lines = lines[1:]
    while lines and re.search(prompt, lines[-1], re.MULTILINE):
        lines = lines[:-1]
    return "\n".join(lines).strip()


class TerminalOutput:
    """One command's output as read three ways."""

    def __init__(self, websocket: str, clipboard: str, ocr_text: str):
        self.websocket = websocket
        self.clipboard = clipboard
        self.ocr_text = ocr_text

    @property
    def text(self) -> str:
        """The canonical reading. Exact, but only trustworthy once `shows` agrees."""
        return self.websocket

    def shows(self, needle: str) -> tuple[bool, str]:
        """True when `needle` is visible in all three readings.

        The websocket and clipboard must contain it after normalisation. OCR is
        allowed to have misread characters, so it passes if it contains the
        needle, or if the whole OCR reading resembles the websocket reading.
        """
        if not needle.strip():
            raise ValueError("needle must not be empty")
        wanted = ocr.normalise(needle)
        in_ws = wanted in ocr.normalise(self.websocket)
        in_clip = wanted in ocr.normalise(self.clipboard)
        in_ocr = wanted in ocr.normalise(self.ocr_text) or ocr.looks_like(self.ocr_text, self.websocket)
        missing = [
            name
            for name, present in (("websocket", in_ws), ("clipboard", in_clip), ("screen (ocr)", in_ocr))
            if not present
        ]
        detail = (
            f"{needle!r} seen in all three readings"
            if not missing
            else f"{needle!r} missing from: {', '.join(missing)}\n"
            f"  websocket: {self.websocket!r}\n"
            f"  clipboard: {self.clipboard!r}\n"
            f"  screen:    {self.ocr_text!r}"
        )
        return (not missing), detail


class WebTerminal:
    """The wssh iframe on a board page."""

    def __init__(self, page, frame_selector: str = "#wssh_if", prompt: str = DEFAULT_PROMPT):
        self.page = page
        self.frame_selector = frame_selector
        self.prompt = prompt
        self._frames: list[bytes | str] = []
        self._last_screen = ""

    # -- lifecycle --

    def attach(self) -> None:
        """Start recording the terminal's WebSocket. Call before navigating."""

        def on_websocket(ws):
            if _WSSH_WS in ws.url:
                ws.on("framereceived", lambda payload: self._frames.append(payload))

        self.page.on("websocket", on_websocket)

    def reset(self) -> None:
        """Forget buffered output -- e.g. after navigating away and back."""
        self._frames.clear()

    def wait_for_prompt(self, timeout: float = 60.0, look_every: float = 3.0) -> None:
        """Block until a prompt is on screen.

        Two ways of telling, because neither is sufficient alone. The
        WebSocket is cheap and exact but is transport, not screen. The screen
        is what a person judges by -- and it is the only one that can see a
        prompt printed before this buffer started, which is the case after a
        reset() or after navigating back to the page, when the only new bytes
        are tmux repainting its status bar.

        Deliberately no keystrokes. Asking an idle shell to print a fresh
        prompt by pressing Enter works, but this is a shared tmux session: if
        another person has a half-typed command on the line, that Enter runs
        it. Looking costs nothing and risks nothing.
        """
        deadline = time.monotonic() + timeout
        next_look = time.monotonic()
        while time.monotonic() < deadline:
            if at_a_prompt(decode_wssh_frames(self._frames), self.prompt):
                return
            if time.monotonic() >= next_look:
                if self._screen_shows_prompt():
                    return
                next_look = time.monotonic() + look_every
            self.page.wait_for_timeout(500)
        raise TimeoutError(
            f"no shell prompt within {timeout}s; the screen reads {self._last_screen!r} "
            f"and the socket sent {decode_wssh_frames(self._frames)!r}"
        )

    def _screen_shows_prompt(self) -> bool:
        """Is there a prompt on the terminal as rendered? What a person checks."""
        try:
            self._last_screen = self._ocr_visible()
        except Exception:  # noqa: BLE001 - nothing to screenshot yet is a reason to keep waiting
            return False
        return at_a_prompt(without_cursor(self._last_screen), self.prompt)

    def wait_until_usable(self, timeout: float = 300.0, settle: float = 5.0) -> None:
        """Keep reconnecting until the terminal both comes back and stays up.

        Reaching a prompt is not enough after a reboot. sshd accepts early in
        boot, before the login wrapper can attach to the shared tmux session,
        so WebSSH connects, draws a prompt, and then the channel closes --
        leaving its login form and "chan closed" on screen. A person tries
        again rather than concluding the board is broken.

        A trivial command is the proof: it round-trips only if the channel is
        still open, and it leaves nothing behind in a session other people
        share.
        """
        deadline = time.monotonic() + timeout
        last = "never tried"
        while True:
            remaining = deadline - time.monotonic()
            try:
                self.reconnect(timeout=max(10.0, min(120.0, remaining)))
                self.run("true", timeout=20.0)
                return
            except Exception as exc:  # noqa: BLE001 - a session that died while booting
                last = f"{type(exc).__name__}: {exc}"
            if time.monotonic() >= deadline:
                raise TimeoutError(f"the terminal never became usable within {timeout}s ({last})")
            self.page.wait_for_timeout(int(settle * 1000))

    # -- interaction --

    def reconnect(self, timeout: float = 300.0, attempt: float = 30.0) -> None:
        """Click the page's own 'reset ssh' button until the terminal comes back.

        One click is not enough after a power cycle. The Pi takes minutes to
        boot, and WebSSH falls back to its blank login form -- "Hostname Port
        Username Password ... Connect" -- whenever auto-connect fails, and
        then sits there. That form means "not yet", not "broken": on a healthy
        board the same click reconnects immediately. A person waits a little
        and clicks reset ssh again, which is what this does, until the
        terminal is really back or the deadline passes.
        """
        deadline = time.monotonic() + timeout
        last = ""
        while True:
            self._frames.clear()
            self._last_screen = ""
            self.page.click("#wssh-connect")
            remaining = deadline - time.monotonic()
            try:
                self.wait_for_terminal(timeout=max(1.0, min(attempt, remaining)))
                break
            except TimeoutError as exc:
                last = str(exc)
                if time.monotonic() >= deadline:
                    raise TimeoutError(
                        f"the terminal never came back within {timeout}s of clicking 'reset ssh' ({last})"
                    ) from exc
                self.page.wait_for_timeout(5000)
        self.wait_for_prompt(timeout=max(10.0, deadline - time.monotonic()))

    def wait_for_terminal(self, timeout: float = 60.0) -> None:
        """Wait for the terminal surface itself to be on the page.

        Clicking "reset ssh" tears the iframe down and builds it again, so for
        a while there is no xterm to read: a person waits for the black
        rectangle to come back before typing into it. Without this the next
        command raced the rebuild and died inside the clipboard read, where
        the failure looked like a broken terminal rather than an early one.
        """
        try:
            self.page.frame_locator(self.frame_selector).locator(".xterm-screen").wait_for(
                state="visible", timeout=timeout * 1000
            )
        except Exception as exc:
            # Quote what the iframe is showing. WebSSH puts "Authentication
            # failed." on screen when it cannot log in, which is the whole
            # diagnosis and is otherwise thrown away.
            said = self.page.frame_locator(self.frame_selector).locator("body").inner_text(timeout=5000)
            raise TimeoutError(f"no terminal within {timeout}s; the iframe reads {said.strip()[:200]!r}") from exc

    def _focus(self):
        frame = self.page.frame_locator(self.frame_selector)
        frame.locator(".xterm-screen").click()
        return frame

    def run(self, command: str, timeout: float = 30.0, settle: float = 1.5) -> TerminalOutput:
        """Type a command, wait for the prompt, and read the output three ways."""
        self.wait_for_terminal()
        self._focus()
        mark = len(self._frames)
        self.page.keyboard.type(command)
        self.page.keyboard.press("Enter")

        deadline = time.monotonic() + timeout
        last_len, quiet_since = -1, None
        while time.monotonic() < deadline:
            raw = decode_wssh_frames(self._frames[mark:])
            if len(raw) != last_len:
                last_len, quiet_since = len(raw), None
            elif at_a_prompt(raw, self.prompt):
                quiet_since = quiet_since or time.monotonic()
                if time.monotonic() - quiet_since >= settle:
                    break
            self.page.wait_for_timeout(250)

        raw = decode_wssh_frames(self._frames[mark:])
        return TerminalOutput(
            websocket=strip_prompt_and_echo(raw, command, self.prompt),
            clipboard=strip_prompt_and_echo(self._copy_visible(), command, self.prompt),
            ocr_text=self._ocr_visible(),
        )

    def exit_status(self) -> int:
        """Ask the shell what the last command returned, the way the site's own demos do."""
        out = self.run("echo $?")
        match = re.search(r"-?\d+", out.text)
        if match is None:
            raise AssertionError(f"could not read an exit status from {out.text!r}")
        return int(match.group())

    # -- the two screen-side readings --

    def _retrying(self, read):
        """Read the terminal surface, once more if it was mid-rebuild.

        WebSSH does not rebuild the iframe once and settle: after "reset ssh"
        the xterm appears, the prompt arrives, and the surface can still be
        torn down and built again underneath. A person waits for it to come
        back and looks again rather than declaring the terminal broken.
        """
        try:
            return read()
        except Exception:  # noqa: BLE001 - a rebuild in progress, not a dead terminal
            self.wait_for_terminal()
            return read()


    def _copy_visible(self, timeout: float = 10.0) -> str:
        """Select the terminal viewport and copy, the way a person grabs output."""
        frame = self.page.frame_locator(self.frame_selector)
        box = self._retrying(lambda: frame.locator(".xterm-screen").bounding_box(timeout=timeout * 1000))
        if box is None:
            return ""
        self.page.mouse.move(box["x"] + 2, box["y"] + 2)
        self.page.mouse.down()
        self.page.mouse.move(box["x"] + box["width"] - 2, box["y"] + box["height"] - 2, steps=8)
        self.page.mouse.up()
        self.page.keyboard.press("Control+Insert")
        return self.page.evaluate("navigator.clipboard.readText()")

    def _ocr_visible(self, timeout: float = 5.0) -> str:
        shot = self._retrying(
            lambda: self.page.frame_locator(self.frame_selector)
            .locator(".xterm-screen")
            .screenshot(timeout=timeout * 1000)
        )
        return ocr.read_text(Image.open(io.BytesIO(shot)), psm=6)
