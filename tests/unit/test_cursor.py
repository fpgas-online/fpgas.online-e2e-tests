"""The terminal's cursor is found in the picture and blanked before OCR; OCR never reads it.

tesseract read xterm's idle block cursor as "9}" on a live run (and as "[]" on
another), which the busy guard took for a visitor's half-typed text, so
scheduled runs skipped at random. The fixtures are crops of the terminal from
that live run of 2026-10-04: one with the focused terminal's filled block
cursor, one with the unfocused terminal's hollow cursor.
"""

from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFont

from e2e import cursor, ocr
from e2e.terminal import DEFAULT_PROMPT, TerminalBusy, TerminalLost, WebTerminal, read_shell_line

FIXTURES = Path(__file__).parents[2] / "fixtures" / "terminal"
CELL = (244, 410, 253, 427)  # where the cursor is in both fixtures


@pytest.mark.parametrize("name", ["idle-block-cursor-a", "idle-block-cursor-b"])
def test_the_cursor_is_found_in_the_real_screenshots_and_only_it(name):
    image = Image.open(FIXTURES / f"{name}-2026-10-04.png")
    assert cursor.find_cursors(image) == [CELL]


@pytest.mark.parametrize("name", ["idle-block-cursor-a", "idle-block-cursor-b"])
def test_an_idle_prompt_with_the_real_cursor_blanked_reads_free(name):
    """The real screens, OCRed after blanking: the prompt has nothing after it."""
    image = Image.open(FIXTURES / f"{name}-2026-10-04.png")
    blanked, boxes = cursor.blank_cursors(image)
    assert boxes == [CELL]
    assert read_shell_line(ocr.read_text(blanked, psm=6)).state == "free"


def test_blanking_leaves_the_text_it_was_not_asked_to_touch():
    image = Image.open(FIXTURES / "idle-block-cursor-a-2026-10-04.png")
    blanked, _ = cursor.blank_cursors(image)
    text = ocr.normalise(ocr.read_text(blanked, psm=6))
    assert "Codename: bookworm" in text and "pi@pi-sw2-p47" in text


# --- synthetic screens: what is, and is not, a cursor ---

FONT = ImageFont.load_default(size=17)


def _screen(text="", cursor_at=None, hollow=False, size=(400, 60)):
    image = Image.new("RGB", size, "black")
    draw = ImageDraw.Draw(image)
    draw.text((4, 4), text, fill="white", font=FONT)
    if cursor_at is not None:
        x = cursor_at
        box = (x, 4, x + 9, 21)
        draw.rectangle(box, outline="white") if hollow else draw.rectangle(box, fill="white")
    return image


def test_a_filled_block_is_a_cursor():
    assert len(cursor.find_cursors(_screen("12:00:00 pi@h:~ $", cursor_at=200))) == 1


def test_a_hollow_rectangle_is_a_cursor():
    assert len(cursor.find_cursors(_screen("12:00:00 pi@h:~ $", cursor_at=200, hollow=True))) == 1


def test_two_cells_wide_is_not_a_cursor():
    """Brackets typed side by side outline a rectangle two cells wide, which no cursor is."""
    image = Image.new("RGB", (60, 40), "black")
    ImageDraw.Draw(image).rectangle((10, 5, 27, 21), outline="white")
    assert cursor.find_cursors(image) == []


def test_bars_drawn_like_typed_brackets_are_not_a_hollow_cursor():
    """A typed "[]" has a stroke where the two glyphs meet, so the inside is not empty."""
    image = Image.new("RGB", (60, 40), "black")
    draw = ImageDraw.Draw(image)
    draw.rectangle((10, 5, 28, 22), outline="white")
    draw.line((19, 5, 19, 22), fill="white")
    assert cursor.find_cursors(image) == []


def test_a_wide_status_bar_is_not_a_cursor():
    image = Image.new("RGB", (400, 40), "black")
    ImageDraw.Draw(image).rectangle((0, 20, 399, 37), fill=(0, 170, 0))
    assert cursor.find_cursors(image) == []


def test_text_typed_after_the_prompt_survives_blanking_and_reads_busy():
    """A visitor's half-typed command, cursor after it: the cursor goes, the command stays."""
    image = _screen("12:00:00 pi@h:~ $ sudo apt", cursor_at=280)
    blanked, boxes = cursor.blank_cursors(image)
    assert len(boxes) == 1
    assert read_shell_line(ocr.read_text(blanked, psm=6)).state == "busy"


# --- the decision, with the screen reading and the cursor's presence stubbed ---


class _Page:
    def __init__(self):
        self.waited = 0

    def wait_for_timeout(self, _ms):
        self.waited += 1


def _terminal(readings):
    """A terminal whose successive screen reads are (text, cursor_seen) pairs; the last repeats."""
    term = WebTerminal.__new__(WebTerminal)
    term.prompt = DEFAULT_PROMPT
    term.page = _Page()
    queue = list(readings)
    term.reads = 0

    def look(**_):
        term.reads += 1
        text, seen = queue.pop(0) if len(queue) > 1 else queue[0]
        term._cursor_seen = seen
        return text

    term._ocr_visible = look
    return term


PROMPT = "13:47:56 pi@pi-sw2-p47:~ $ "


def test_an_idle_prompt_is_free_whether_or_not_the_cursor_is_in_this_shot():
    _terminal([(PROMPT, True)]).refuse_if_busy()
    _terminal([(PROMPT, False)]).refuse_if_busy()  # the blink's off phase


def test_text_after_the_prompt_with_a_cursor_found_is_a_visitor():
    with pytest.raises(TerminalBusy):
        _terminal([(PROMPT + "sudo apt", True)]).refuse_if_busy()


def test_a_blinking_cursor_is_looked_for_again_and_the_shot_that_has_it_decides():
    term = _terminal([(PROMPT + "9}", False), (PROMPT, True)])
    term.refuse_if_busy()
    assert term.reads == 2


def test_text_after_the_prompt_with_no_cursor_in_any_look_is_a_failure_not_a_skip():
    term = _terminal([(PROMPT + "9}", False)])
    with pytest.raises(TerminalLost, match="no cursor was found") as caught:
        term.refuse_if_busy()
    assert not isinstance(caught.value, TerminalBusy)
    assert term.reads == 4
