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

    def wait_for_prompt(self, timeout: float = 60.0, nudge_after: float = 6.0, nudge_every: float = 10.0) -> None:
        """Block until the shell shows a prompt, pressing Enter if it stays quiet.

        A shell already sitting at a prompt has nothing left to say. After
        reset(), or after navigating back to the page, the prompt was printed
        before this buffer started and the only new bytes are tmux repainting
        its status bar -- so waiting on the stream alone waits forever for
        something that already happened, while the screen plainly shows a
        prompt. Pressing Enter is what a person does when they are not sure a
        terminal is alive; it makes the shell print a fresh prompt, and costs
        one blank line in the shared tmux session.

        The grace period keeps the nudge out of the way of a normal login,
        which reaches its first prompt in about 5 seconds.
        """
        deadline = time.monotonic() + timeout
        next_nudge = time.monotonic() + nudge_after
        while time.monotonic() < deadline:
            if at_a_prompt(decode_wssh_frames(self._frames), self.prompt):
                return
            if time.monotonic() >= next_nudge:
                self._press_enter()
                next_nudge = time.monotonic() + nudge_every
            self.page.wait_for_timeout(500)
        raise TimeoutError(f"no shell prompt within {timeout}s; saw {decode_wssh_frames(self._frames)!r}")

    def _press_enter(self) -> None:
        """Ask an idle shell for a fresh prompt.

        Never fatal and never slow: a terminal that is still connecting has
        nothing to click, and that is a reason to keep waiting rather than a
        different error to report. The short click timeout matters --
        Playwright's default is 30s, which would swallow the caller's budget.
        """
        try:
            frame = self.page.frame_locator(self.frame_selector)
            frame.locator(".xterm-screen").click(timeout=2000)
            self.page.keyboard.press("Enter")
        except Exception:  # noqa: BLE001 - any failure here just means "not yet"
            pass

    def reconnect(self) -> None:
        """Click the page's own 'reset ssh' button, as a person would."""
        self._frames.clear()
        self.page.click("#wssh-connect")
        self.wait_for_prompt()

    # -- interaction --

    def _focus(self):
        frame = self.page.frame_locator(self.frame_selector)
        frame.locator(".xterm-screen").click()
        return frame

    def run(self, command: str, timeout: float = 30.0, settle: float = 1.5) -> TerminalOutput:
        """Type a command, wait for the prompt, and read the output three ways."""
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

    def _copy_visible(self) -> str:
        """Select the terminal viewport and copy, the way a person grabs output."""
        frame = self.page.frame_locator(self.frame_selector)
        box = frame.locator(".xterm-screen").bounding_box()
        if box is None:
            return ""
        self.page.mouse.move(box["x"] + 2, box["y"] + 2)
        self.page.mouse.down()
        self.page.mouse.move(box["x"] + box["width"] - 2, box["y"] + box["height"] - 2, steps=8)
        self.page.mouse.up()
        self.page.keyboard.press("Control+Insert")
        return self.page.evaluate("navigator.clipboard.readText()")

    def _ocr_visible(self) -> str:
        shot = self.page.frame_locator(self.frame_selector).locator(".xterm-screen").screenshot()
        return ocr.read_text(Image.open(io.BytesIO(shot)), psm=6)
