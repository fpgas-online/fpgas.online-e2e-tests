import pytest

from e2e.terminal import (
    DEFAULT_PROMPT,
    TerminalBusy,
    TerminalLost,
    TerminalOutput,
    WebTerminal,
    at_a_prompt,
    decode_wssh_frames,
    read_shell_line,
    strip_prompt_and_echo,
    without_cursor,
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


class _FakeKeyboard:
    def __init__(self):
        self.pressed = []

    def press(self, key):
        self.pressed.append(key)

    def type(self, text):
        self.pressed.append(text)


class _FakePage:
    """Just enough page for wait_for_prompt, and a keyboard that records abuse."""

    def __init__(self):
        self.keyboard = _FakeKeyboard()
        self.clicks = []

    def click(self, selector):
        self.clicks.append(selector)

    def wait_for_timeout(self, _ms):
        pass


def _terminal(page, frames, screen):
    term = WebTerminal.__new__(WebTerminal)
    term.frame_selector = "#wssh_if"
    term.prompt = DEFAULT_PROMPT
    term._frames = list(frames)
    term._last_screen = ""
    term.page = page
    term._ocr_visible = lambda **_: screen
    return term


def test_wait_for_prompt_believes_the_screen_when_the_socket_is_silent():
    """A shell already at a prompt has nothing left to say.

    After reset(), or after navigating back, the prompt was printed before
    this buffer started and the only new bytes are tmux repainting its status
    bar -- but the prompt is plainly there on screen, which is what a person
    judges by.
    """
    page = _FakePage()
    status_bar_only = [b"\x1b[30m\x1b[42m\x1b[24;1H[default-20:bash*    pi7 01:43am\x1b(B\x1b[m"]
    term = _terminal(page, status_bar_only, screen="07:04:46 pi@pi7:~ $ \n")

    term.wait_for_prompt(timeout=2.0)


def test_wait_for_prompt_never_types_into_a_shared_session():
    """The terminal is a shared tmux session.

    Pressing Enter to make an idle shell print a prompt would submit whatever
    another person has half-typed on that line. Looking costs nothing.
    """
    page = _FakePage()
    term = _terminal(page, frames=[], screen="")

    with pytest.raises(TimeoutError):
        term.wait_for_prompt(timeout=0.5)

    assert page.keyboard.pressed == []


def test_wait_for_prompt_timeout_quotes_the_screen_and_the_socket():
    """A person reporting a dead terminal says what it showed them."""
    page = _FakePage()
    term = _terminal(page, frames=[b"Authentication failed."], screen="socket closed.")

    with pytest.raises(TimeoutError) as caught:
        term.wait_for_prompt(timeout=0.5)

    assert "socket closed." in str(caught.value)
    assert "Authentication failed." in str(caught.value)


def test_a_prompt_is_still_a_prompt_with_the_cursor_drawn_after_it():
    """Captured from ps1 pi7 on 2026-09-13.

    xterm draws the cursor as a filled block and tesseract reads it as "[]".
    Left in place it defeated the end-of-line anchor, and the suite called a
    terminal dead while quoting a screen with a prompt plainly on it.
    """
    screen = "07:26:16 pi@pi7:~ $ cat /proc/uptime\n835.20 3061.42\n07:38:03 pi@pi7:~ $ []\n"
    assert not at_a_prompt(screen)
    assert at_a_prompt(without_cursor(screen))


def test_reconnect_clicks_reset_ssh_again_while_webssh_shows_its_login_form():
    """After a power cycle the Pi is still booting, so the first click fails.

    WebSSH falls back to a blank login form when auto-connect fails and then
    sits there. That means "not yet", not "broken" -- the same click works
    immediately on a healthy board -- so a person waits and clicks again.
    """
    page = _FakePage()
    term = _terminal(page, frames=[], screen="")
    term.wait_for_prompt = lambda timeout=60.0: None

    attempts = []

    def not_yet(timeout=60.0):
        attempts.append(timeout)
        if len(attempts) < 3:
            raise TimeoutError("no terminal; the iframe reads 'Hostname Port Username Password ... Connect'")

    term.wait_for_terminal = not_yet
    term.reconnect(timeout=60.0, attempt=1.0)

    assert page.clicks == ["#wssh-connect"] * 3


def test_reconnect_gives_up_with_what_the_iframe_was_showing():
    page = _FakePage()
    term = _terminal(page, frames=[], screen="")

    def never(timeout=60.0):
        raise TimeoutError("no terminal; the iframe reads 'Hostname Port Username Password ... Connect'")

    term.wait_for_terminal = never
    with pytest.raises(TimeoutError) as caught:
        term.reconnect(timeout=2.0, attempt=0.5)

    assert "Hostname" in str(caught.value)


def test_wait_until_usable_tries_again_when_the_channel_closes_after_connecting():
    """Captured from ps1 pi7 after a real power cycle on 2026-09-13.

    WebSSH connected, drew a prompt, and the channel closed moments later --
    sshd accepts before the login wrapper can attach to the shared tmux
    session. The iframe was left showing its login form and "chan closed".
    """
    page = _FakePage()
    term = _terminal(page, frames=[], screen="")
    term.reconnect = lambda timeout=60.0: None

    tries = []

    def flaky_run(command, timeout=30.0):
        tries.append(command)
        if len(tries) < 3:
            raise TimeoutError("no terminal; the iframe reads '... Connect Reset\\nchan closed'")

    term.run = flaky_run
    term.wait_until_usable(timeout=60.0, settle=0.01)

    assert tries == ["true"] * 3


# The whole viewport as the clipboard and OCR readings see it: an earlier
# prompt, an earlier command, and then the one just typed. Cutting at the
# first echo would leave "pi7" from the prompts in the reading; cutting at the
# last leaves only what `hostname` printed.
VIEWPORT = (
    "07:38:03 pi@pi7:~ $ uptime -p\n"
    "up 3 days, 2 hours\n"
    "07:38:10 pi@pi7:~ $ hostname\n"
    "pi7\n"
    "07:38:11 pi@pi7:~ $ "
)


def test_strip_prompt_and_echo_cuts_at_the_last_echo_of_the_command():
    assert strip_prompt_and_echo(VIEWPORT, "hostname") == "pi7"


def test_strip_prompt_and_echo_accepts_an_ocr_misread_of_the_echo():
    misread = VIEWPORT.replace("$ hostname", "$ hostnane")
    assert strip_prompt_and_echo(misread, "hostname") == "pi7"


def test_strip_prompt_and_echo_does_not_take_a_short_word_as_the_echo():
    """A two-letter command must match exactly; fuzzy matching would find it everywhere."""
    text = "pi@pi7:~ $ ls\nfoo\npi@pi7:~ $ "
    assert strip_prompt_and_echo(text, "ls") == "foo"


def test_a_needle_that_only_sits_in_the_prompt_is_not_shown():
    """The hostname is in every prompt. Sliced readings make that count for nothing."""
    out = TerminalOutput(
        websocket=strip_prompt_and_echo("pi@pi7:~ $ true\npi@pi7:~ $ ", "true"),
        clipboard=strip_prompt_and_echo("pi@pi7:~ $ true\npi@pi7:~ $ ", "true"),
        ocr_text=strip_prompt_and_echo("pi@pi7:~ $ true\npi@pi7:~ $ ", "true"),
    )
    shown, _ = out.shows("pi7")
    assert not shown


def test_output_lines_are_the_websocket_reading_line_by_line():
    assert TerminalOutput("pi7\r\n", "pi7", "pi7").lines() == ["pi7"]


def test_a_half_typed_command_on_the_prompt_line_is_named():
    """Seen on ps1 pi7, 2026-09-14: a shared session with someone's command waiting."""
    from e2e.terminal import describe_busy_shell

    screen = "03:24:27 pi@pi7:~ $ echo $?\n0\n03:26:04 pi@pi7:~/Demos/counter_test $ sudo apt install pipx\n"
    assert "'sudo apt install pipx'" in describe_busy_shell(screen)


def test_a_free_prompt_is_not_described_as_busy():
    from e2e.terminal import describe_busy_shell

    assert describe_busy_shell("03:26:04 pi@pi7:~ $ []\n") == ""
    assert describe_busy_shell("") == ""


# -- refusing to type into a terminal someone is using ------------------------


class _RespondingKeyboard(_FakeKeyboard):
    """Records keystrokes; Enter makes the shell answer, as a real one would."""

    def __init__(self, term):
        super().__init__()
        self.term = term

    def press(self, key):
        super().press(key)
        if key == "Enter":
            self.term._frames.append(b"hostname\r\npi7\r\n03:30:00 pi@pi7:~ $ ")


def _ready_terminal(screen):
    page = _FakePage()
    term = _terminal(page, frames=[], screen=screen)
    page.keyboard = _RespondingKeyboard(term)
    term.wait_for_terminal = lambda timeout=60.0: None
    term._focus = lambda: None
    term._copy_visible = lambda: "pi7"
    return page, term


def test_run_types_and_presses_enter_when_the_prompt_line_is_empty():
    page, term = _ready_terminal("03:26:04 pi@pi7:~ $ []\n[default-10:bash*  pi7 02:28pm\n")

    out = term.run("hostname", settle=0)

    assert page.keyboard.pressed == ["hostname", "Enter"]
    assert out.websocket == "pi7"


def test_run_types_nothing_when_someone_has_a_half_typed_command_on_the_line():
    """Without the guard `type` appends to the line and Enter runs the visitor's command plus ours."""
    page, term = _ready_terminal("03:26:04 pi@pi7:~/Demos $ sudo apt install pipx\n")

    with pytest.raises(TerminalBusy) as caught:
        term.run("hostname", settle=0)

    assert "'sudo apt install pipx'" in str(caught.value)
    assert page.keyboard.pressed == []


def test_run_types_nothing_and_fails_when_no_prompt_line_is_visible():
    """No prompt at all is a dead terminal, not a visitor: a failure quoting the screen."""
    page, term = _ready_terminal("Reading package lists...\nBuilding dependency tree...\n")

    with pytest.raises(TerminalLost, match="Building dependency tree") as caught:
        term.run("hostname", settle=0)

    assert not isinstance(caught.value, TerminalBusy)
    assert page.keyboard.pressed == []


def test_a_prompt_seen_moments_ago_that_is_then_gone_is_a_failure_not_a_skip():
    page, term = _ready_terminal("03:26:04 pi@pi7:~ $ []\n")
    term.wait_for_prompt(timeout=2.0)  # the prompt is there

    term._ocr_visible = lambda **_: "Authentication failed.\n"  # and then it is not

    with pytest.raises(TerminalLost, match="Authentication failed"):
        term.run("hostname", settle=0)
    assert page.keyboard.pressed == []


def test_run_focuses_the_terminal_before_looking_and_looks_before_typing():
    page, term = _ready_terminal("03:26:04 pi@pi7:~ $ []\n")
    order = []
    term._focus = lambda: order.append("focus")
    term._ocr_visible = lambda **_: order.append("look") or "03:26:04 pi@pi7:~ $ []\n"
    page.keyboard.type = lambda text: order.append("type")

    term.run("hostname", settle=0)

    assert order[:3] == ["focus", "look", "type"]


def test_wait_for_prompt_says_busy_when_the_only_prompt_line_has_text_after_it():
    page = _FakePage()
    term = _terminal(page, frames=[], screen="03:26:04 pi@pi7:~ $ sudo apt install pipx\n")

    with pytest.raises(TerminalBusy, match="a visitor is using the terminal: 'sudo apt install pipx'"):
        term.wait_for_prompt(timeout=0.5)
    assert page.keyboard.pressed == []


def test_wait_for_prompt_with_no_prompt_line_at_all_is_still_a_timeout():
    """Dead stays a failure exactly as before."""
    term = _terminal(_FakePage(), frames=[], screen="Authentication failed.\n")

    with pytest.raises(TimeoutError) as caught:
        term.wait_for_prompt(timeout=0.5)
    assert not isinstance(caught.value, TerminalBusy)


def test_exit_status_is_refused_too_when_the_line_is_not_empty():
    page, term = _ready_terminal("03:26:04 pi@pi7:~ $ ls -l\n")

    with pytest.raises(TerminalBusy):
        term.exit_status()

    assert page.keyboard.pressed == []


PROMPT = "03:26:04 pi@pi7:~ $ "
# The real status line (fpgas.online-setup-pi onpi/tmux/tmux.conf): [session number] windows, hostname, %I:%M%p.
STATUS = "[3] 0:h- 1:bash*                    pi-sw2-p46 10:50PM"


@pytest.mark.parametrize(
    ("screen", "state"),
    [
        # free: nothing after the prompt, or exactly the cursor block OCR reads as "[]"
        (PROMPT + "\n", "free"),
        (PROMPT + "[]\n", "free"),
        ("03:26:04 pi@pi7:~ $\n", "free"),
        ("03:26:04 pi@pi7:~ # \n", "free"),
        ("03:24:27 pi@pi7:~ $ echo hi\nhi\n" + PROMPT + "[]\n", "free"),
        # a single stray character is a visitor's first keystroke, never a cursor
        (PROMPT + "|\n", "busy"),
        (PROMPT + "_\n", "busy"),
        (PROMPT + "[\n", "busy"),
        (PROMPT + "]\n", "busy"),
        (PROMPT + "l\n", "busy"),
        (PROMPT + "[][]\n", "busy"),
        (PROMPT + "ls []\n", "busy"),
        (PROMPT + "echo $HOME\n", "busy"),
        ("03:24:27 pi@pi7:~ $ []\n03:26:04 pi@pi7:~ $ vi x\n", "busy"),
        ("\x1b[32mpi@pi7\x1b[m:~ $ \x1b[Kls\n", "busy"),
        # a command typed on the line that is running: its output is under it
        (PROMPT + "sleep 99\nstill going\n", "busy"),
        (PROMPT + "sudo apt install pipx\nReading package lists...\n", "busy"),
        # a broken board never reads as a visitor: text under the prompt that is a closed session,
        # an error or a system message fails, whether or not the line above has text
        (PROMPT + "[]\nConnection to pi7 closed.\n", "broken"),
        (PROMPT + "ls\nbash: /usr/bin/ls: Stale file handle\n", "broken"),
        (PROMPT + "[]\nbash: /usr/bin/ls: Stale file handle\n", "broken"),
        (PROMPT + "[]\nBroadcast message from root@pi7 (Sun 2026-10-04 22:00):\nThe system is going down\n", "broken"),
        (PROMPT + "[]\n[  123.456789] mmc0: error -110 whilst initialising SD card\n", "broken"),
        (PROMPT + "[]\nls: reading directory '.': Input/output error\n", "broken"),
        (PROMPT + "[]\ntouch: cannot touch 'x': Read-only file system\n", "broken"),
        (PROMPT + "apt install x\nE: Failed to fetch http://x  Read-only file system\n", "broken"),
        # anything else under an empty prompt is unrecognised: when in doubt, not a visitor
        (PROMPT + "[]\n>>> import os\n", "unknown"),
        ("03:26:04 pi@pi7:~/a/very/long/path $ []\nsudo apt install pipx\n", "unknown"),
        # no prompt line at all
        ("no prompt here\n", "none"),
        (">>> import os\n", "none"),
        ("", "none"),
    ],
)
def test_read_shell_line_state(screen, state):
    assert read_shell_line(screen).state == state


@pytest.mark.parametrize(
    "status",
    [
        "[3] 0:h- 1:bash*                    pi-sw2-p46 10:50PM",  # the real one
        "[12] 0:h 1:bash- 2:bash*     pi-sw2-p46 07:05AM",  # several windows, zero-padded hour
        "[3] 0:h 1:bash*   pi7 22:50",  # 24-hour
        "[default-10:bash*            pi2 02:28pm",  # the older capture
        "3 0:h- 1:bash   pi-sw2-p46 10:50PM",  # OCR dropped the brackets and the star
        "[3 0:h- 1:bash*   pi-sw2-p46 10:5OPM",  # OCR read a zero as a letter
        "[3] 0:h- 1:bash*   pi-sw2-p46 10:50PM |",  # trailing OCR junk
        "[3] 0:h- 1:bash*   pi-sw2-p46 10:S0PM",  # S for 5
        "[3] 0:h- 1:bash*   pi-sw2-p46 l0:50PM",  # l for 1
        "[3] 0:h- 1:bash*   pi-sw2-p46 IO:5OPM",  # I for 1, O for 0
        "[3] 0:h- 1:bash*   pi-sw2-p46 O8:BZPM",  # O for 0, B for 8, Z for 2
        "[3] 0:h- 1:bash*   pi-sw2-p46 |0:50PM",  # | for 1
        "[3] 0:h   pi-sw2-p46 10:50PM",  # one window only
    ],
)
def test_the_last_row_is_recognised_as_a_status_line_by_shape(status):
    assert read_shell_line(PROMPT + "[]\n" + status + "\n").state == "free"


def test_a_status_line_is_only_ignored_on_the_last_row():
    """A clock anywhere else is text: the same line above the last row is not a status line."""
    screen = PROMPT + "[]\n" + STATUS + "\nsomething else\n"
    assert read_shell_line(screen).state == "unknown"


@pytest.mark.parametrize(
    "row",
    [
        "[3] 0:h- 1:bash* pi-sw2-p46 garbled",  # tmux shape, no clock
        "[3] pi-sw2-p46 10:50PM",  # no window entry
        "[3] 0:h- 1:bash*",  # no host or clock
        "pi-sw2-p46 10:50PM",  # host and clock only
    ],
)
def test_a_last_row_that_is_not_the_whole_tmux_shape_is_not_a_status_row(row):
    assert read_shell_line(PROMPT + "[]\n" + row + "\n").state == "unknown"


@pytest.mark.parametrize(
    "row",
    [
        "[exited] 0:x pi7 10:50",  # tmux-shaped, but the session is not a number
        "Next 0:30 pi7 10:50PM",  # no session number; "30" is a time, not a window name
        "[3] 0:30 pi7 10:50PM",  # a window name has a letter in it
        "[main] 0:h 1:bash* pi7 10:50PM",  # a named session is not the one tmux.conf creates
    ],
)
def test_a_row_with_only_the_look_of_a_status_line_is_not_dropped_as_one(row):
    """The line above it must not read as free: these are unrecognised text, so a failure."""
    assert read_shell_line(PROMPT + "[]\n" + row + "\n").state == "unknown"


@pytest.mark.parametrize(
    "row",
    [
        # a clock at the end is not what makes a status row: none of these may be dropped as one
        "Connection to pi closed at 10:50",
        "Connection to pi7 closed by remote host at 10:50PM",
        "Broadcast message from root@pi7 (Sun 2026-10-04 22:00): the system is going down at 22:50",
        "[  123.456789] eth0: link is down 10:50",
        "Remote side unexpectedly dropped the session at 10:50",
        "bash: /usr/bin/ls: Stale file handle 10:50",
    ],
)
def test_a_fault_ending_in_a_time_is_never_swallowed_as_the_status_row(row):
    assert read_shell_line(PROMPT + "[]\n" + row + "\n").state in ("broken", "unknown")


def test_a_fault_matching_a_broken_pattern_is_checked_before_the_status_shape():
    """Even a row with the whole tmux shape is not discarded if a fault pattern matches it.

    Here a window happens to be named "error": the broken check comes first, so the row
    stays in the screen and the result is a failure, not a silent drop.
    """
    row = "[3] 0:h- 1:error* pi7 10:50PM"
    assert read_shell_line(PROMPT + "[]\n" + row + "\n").state == "broken"


@pytest.mark.parametrize(
    "row",
    [
        "Connection to pi closed at 10:50",
        "Broadcast message from root@pi7 (Sun 2026-10-04 22:00): the system is going down at 22:50",
        "[  123.456789] eth0: link is down 10:50",
    ],
)
def test_run_types_nothing_and_fails_for_a_fault_ending_in_a_time(row):
    page, term = _ready_terminal(PROMPT + "[]\n" + row + "\n")

    with pytest.raises(TerminalLost) as caught:
        term.run("hostname", settle=0)

    assert not isinstance(caught.value, TerminalBusy)
    assert page.keyboard.pressed == []


def test_the_read_quotes_what_it_judged():
    line = read_shell_line(PROMPT + "sudo apt install pipx\n" + STATUS + "\n")
    assert line.state == "busy" and line.text == "sudo apt install pipx"


def test_run_fails_and_types_nothing_for_a_closed_session_under_the_prompt():
    """The stale-NFS breakage and a dropped session look like text under the prompt; they are not a visitor."""
    page, term = _ready_terminal(PROMPT + "[]\nbash: /usr/bin/ls: Stale file handle\n" + STATUS + "\n")

    with pytest.raises(TerminalLost, match="Stale file handle") as caught:
        term.run("hostname", settle=0)

    assert not isinstance(caught.value, TerminalBusy)
    assert page.keyboard.pressed == []


def test_the_busy_reason_quotes_the_screen_it_was_judged_from():
    page, term = _ready_terminal(PROMPT + "sudo apt install pipx\n" + STATUS + "\n")

    with pytest.raises(TerminalBusy) as caught:
        term.run("hostname", settle=0)

    assert "the screen reads" in str(caught.value) and "pi-sw2-p46" in str(caught.value)
    assert page.keyboard.pressed == []
