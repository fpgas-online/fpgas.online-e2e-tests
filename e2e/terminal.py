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
import json
import re
import time

from PIL import Image

from e2e import ocr

DEFAULT_PROMPT = r"[$#] $"
_WSSH_WS = "/wssh/ws"


def decode_wssh_frames(frames: list[str]) -> str:
    """Concatenate the terminal output carried by WebSSH's {"data": ...} frames."""
    out = []
    for frame in frames:
        try:
            payload = json.loads(frame)
        except (TypeError, ValueError):
            continue
        if isinstance(payload, dict) and isinstance(payload.get("data"), str):
            out.append(payload["data"])
    return "".join(out)


def strip_prompt_and_echo(text: str, command: str, prompt: str = DEFAULT_PROMPT) -> str:
    """Drop the echoed command and the prompt the shell printed afterwards."""
    body = ocr.strip_ansi(text)
    lines = [line.rstrip("\r") for line in body.split("\n")]
    if lines and command.strip() and command.strip() in lines[0]:
        lines = lines[1:]
    while lines and re.search(prompt, lines[-1]):
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
        self._frames: list[str] = []

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

    def wait_for_prompt(self, timeout: float = 60.0) -> None:
        """Block until the shell has printed a prompt."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if re.search(self.prompt, decode_wssh_frames(self._frames).rstrip()):
                return
            self.page.wait_for_timeout(500)
        raise TimeoutError(f"no shell prompt within {timeout}s; saw {decode_wssh_frames(self._frames)!r}")

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
            elif re.search(self.prompt, raw.rstrip()):
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
