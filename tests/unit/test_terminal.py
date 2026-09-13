import pytest

from e2e.terminal import (
    DEFAULT_PROMPT,
    TerminalOutput,
    WebTerminal,
    decode_wssh_frames,
    strip_prompt_and_echo,
)

# Captured off wss://ps1.fpgas.online/wssh/ws on 2026-09-12. WebSSH sends the
# server->client direction as BINARY frames of raw terminal bytes -- its own
# client does read_file_as_text(msg.data, term_write, decoder) and writes them
# straight to xterm. Only the client->server direction is JSON.
REAL_FRAME = b"Linux pi2 6.12.75+rpt-rpi-v7 #1 SMP Raspbian 1:6.12.75-1+rpt1 (2026-03-11) armv7l\r\n"


def test_decode_wssh_frames_decodes_the_binary_frames_webssh_really_sends():
    assert decode_wssh_frames([REAL_FRAME]) == REAL_FRAME.decode()


def test_decode_wssh_frames_concatenates_in_order():
    assert decode_wssh_frames([b"hel", b"lo\r\n"]) == "hello\r\n"


def test_decode_wssh_frames_accepts_text_frames_too():
    assert decode_wssh_frames([b"a", "b"]) == "ab"


def test_decode_wssh_frames_does_not_raise_on_undecodable_bytes():
    """A frame can split a multi-byte character; losing one glyph beats an exception."""
    assert "ok" in decode_wssh_frames([b"\xff\xfeok"])


def test_strip_prompt_and_echo_removes_the_typed_command_and_the_trailing_prompt():
    raw = "cat /proc/uptime\r\n812.34 1600.11\r\npi@pi-sw2-p16:~ $ "
    assert strip_prompt_and_echo(raw, "cat /proc/uptime") == "812.34 1600.11"


def test_output_shows_a_needle_present_in_all_three_readings():
    out = TerminalOutput(
        websocket="total 2192119 top.bit",
        clipboard="total 2192119 top.bit",
        ocr_text="total 2l92ll9 top.bit",
    )
    shown, detail = out.shows("top.bit")
    assert shown, detail


def test_output_does_not_show_a_needle_missing_from_the_clipboard():
    out = TerminalOutput(
        websocket="total 2192119 top.bit",
        clipboard="",
        ocr_text="total 2192119 top.bit",
    )
    shown, detail = out.shows("top.bit")
    assert not shown
    assert "clipboard" in detail


def test_output_accepts_ocr_that_merely_resembles_the_websocket_text():
    """OCR mangles letters; the reading must still be recognisable, not exact."""
    out = TerminalOutput(
        websocket="Arty pmod wire test passed",
        clipboard="Arty pmod wire test passed",
        ocr_text="Arty pmod wlre test passed",
    )
    shown, detail = out.shows("wire test passed")
    assert shown, detail


def test_output_text_prefers_the_websocket_reading():
    out = TerminalOutput(websocket="a", clipboard="b", ocr_text="c")
    assert out.text == "a"


def test_ansi_sequences_do_not_hide_a_needle():
    out = TerminalOutput(
        websocket="\x1b[0;32mpi@host\x1b[0m:~ $ done",
        clipboard="pi@host:~ $ done",
        ocr_text="pi@host:~ $ done",
    )
    shown, _ = out.shows("done")
    assert shown


@pytest.mark.parametrize("needle", ["", "   "])
def test_shows_rejects_an_empty_needle(needle):
    out = TerminalOutput(websocket="x", clipboard="x", ocr_text="x")
    with pytest.raises(ValueError):
        out.shows(needle)


class _FakeClickable:
    def click(self, **_kwargs):
        pass


class _FakeFrame:
    def locator(self, _selector):
        return _FakeClickable()


class _FakeKeyboard:
    def __init__(self, on_enter):
        self._on_enter = on_enter

    def press(self, key):
        if key == "Enter":
            self._on_enter()


class _FakePage:
    """Just enough page for wait_for_prompt: a clickable terminal and a keyboard."""

    def __init__(self, on_enter=lambda: None, focusable=True):
        self.keyboard = _FakeKeyboard(on_enter)
        self._focusable = focusable
        self.enters = 0

    def frame_locator(self, _selector):
        if not self._focusable:
            raise RuntimeError("no terminal to click: the iframe is still connecting")
        return _FakeFrame()

    def wait_for_timeout(self, _ms):
        pass


def test_wait_for_prompt_presses_enter_when_the_shell_is_already_sitting_at_one():
    """An idle shell has nothing left to say.

    After reset(), or after navigating back to the page, the prompt was printed
    before we started reading and the only new bytes are tmux repainting its
    status bar. Pressing Enter is what a person does when unsure a terminal is
    alive, and it makes the shell print a fresh prompt we can see.
    """
    terminal = WebTerminal.__new__(WebTerminal)
    terminal.frame_selector = "#wssh_if"
    terminal.prompt = DEFAULT_PROMPT
    terminal._frames = [b"\x1b[30m\x1b[42m\x1b[24;1H[default-20:bash*    pi7 01:43am\x1b(B\x1b[m"]
    terminal.page = _FakePage(on_enter=lambda: terminal._frames.append(b"\r\npi@pi7:~ $ "))

    terminal.wait_for_prompt(timeout=2.0, nudge_after=0.0)


def test_wait_for_prompt_survives_a_terminal_that_is_not_clickable_yet():
    """The nudge must never turn a timeout into a different, misleading error."""
    terminal = WebTerminal.__new__(WebTerminal)
    terminal.frame_selector = "#wssh_if"
    terminal.prompt = DEFAULT_PROMPT
    terminal._frames = []
    terminal.page = _FakePage(focusable=False)

    with pytest.raises(TimeoutError):
        terminal.wait_for_prompt(timeout=0.5, nudge_after=0.0)
