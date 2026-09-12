"""Prompt detection, against real terminal bytes.

The sample below is trimmed from a real capture off
wss://ps1.fpgas.online/wssh/ws on 2026-09-12. Two properties of the real thing
make naive matching fail, and both are represented here:

  * the prompt is wrapped in ANSI colour and followed by more escapes, so the
    text must be stripped before matching;
  * the session runs inside tmux, which redraws constantly, so the buffer
    almost never *ends* at a prompt -- an end-of-string anchor never matches.
"""

from e2e.terminal import DEFAULT_PROMPT, at_a_prompt, strip_prompt_and_echo

REAL = (
    "\x1b[?25l\x1b[H06:24:59 \x1b[32m\x1b[1mpi@pi2\x1b(B\x1b[m:\x1b[34m\x1b[1m~ $\x1b(B\x1b[m "
    "cd ~/Demos/counter_test\x1b[K\r\n"
    "06:25:33 \x1b[32m\x1b[1mpi@pi2\x1b(B\x1b[m:\x1b[34m\x1b[1m~/Demos/counter_test $\x1b(B\x1b[m \x1b[K"
    "\x1b[30m\x1b[42m\r\n[default-10:bash*            pi2 02:28pm \x1b(B\x1b[m\x1b[?12l\x1b[?25h\x1b[9;40H"
)

BANNER_ONLY = (
    "Linux pi2 6.12.75+rpt-rpi-v7 #1 SMP Raspbian armv7l\r\n"
    "Last login: Sat Sep 12 14:27:38 2026 from 10.21.0.1\r\n"
)


def test_a_real_buffer_is_recognised_as_being_at_a_prompt():
    assert at_a_prompt(REAL)


def test_a_buffer_showing_only_the_login_banner_is_not_at_a_prompt():
    assert not at_a_prompt(BANNER_ONLY)


def test_an_empty_buffer_is_not_at_a_prompt():
    assert not at_a_prompt("")


def test_the_default_pattern_matches_a_plain_prompt_with_no_colour():
    assert at_a_prompt("pi@pi-sw2-p16:~ $ ")


def test_a_root_prompt_counts_too():
    assert at_a_prompt("root@pi2:/etc # ")


def test_strip_prompt_and_echo_handles_the_real_coloured_prompt():
    raw = (
        "cat /proc/uptime\r\n812.34 1600.11\r\n"
        "06:25:33 \x1b[32m\x1b[1mpi@pi2\x1b(B\x1b[m:\x1b[34m\x1b[1m~ $\x1b(B\x1b[m \x1b[K"
    )
    assert strip_prompt_and_echo(raw, "cat /proc/uptime") == "812.34 1600.11"


def test_the_default_prompt_pattern_is_a_string_others_can_override():
    assert isinstance(DEFAULT_PROMPT, str)
