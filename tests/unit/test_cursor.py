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


def test_text_that_stays_the_same_in_every_look_with_no_cursor_found_is_a_visitor_typing_against_it():
    """Typed text merged with the cursor leaves no separate block; stable text on the last prompt row is busy."""
    term = _terminal([(PROMPT + "l", False)])
    with pytest.raises(TerminalBusy, match="a visitor is using the terminal") as caught:
        term.refuse_if_busy()
    assert "13:47:56 pi@pi-sw2-p47" in str(caught.value)  # the reason quotes the screen
    assert term.reads == 4


def test_text_that_changes_between_looks_with_no_cursor_found_is_a_failure_not_a_skip():
    term = _terminal([(PROMPT + "9}", False), (PROMPT + "9)", False), (PROMPT + "l}", False), (PROMPT + "9}", False)])
    with pytest.raises(TerminalLost, match="changed between") as caught:
        term.refuse_if_busy()
    assert not isinstance(caught.value, TerminalBusy)


def test_a_fault_under_stable_text_with_no_cursor_found_is_never_a_visitor():
    term = _terminal([(PROMPT + "ls\nbash: /usr/bin/ls: Stale file handle", False)])
    with pytest.raises(TerminalLost) as caught:
        term.refuse_if_busy()
    assert not isinstance(caught.value, TerminalBusy)


# --- a glyph abutting the cursor must survive the blanking ---


def _abutting(glyph, gap):
    """A prompt, then `glyph`, then the cursor `gap` pixels after the glyph's own ink ends."""
    image = Image.new("RGB", (400, 60), "black")
    draw = ImageDraw.Draw(image)
    draw.text((4, 4), "12:00:00 pi@h:~ $ ", fill="white", font=FONT)
    x = 4 + round(draw.textlength("12:00:00 pi@h:~ $ ", font=FONT))
    draw.text((x, 4), glyph, fill="white", font=FONT)
    ink_right = max(i for i in range(image.width) if any(image.getpixel((i, y))[0] > 80 for y in range(60)))
    left = ink_right + 1 + gap
    draw.rectangle((left, 4, left + 8, 20), fill="white")
    return image, (left, 4, left + 9, 21)


@pytest.mark.parametrize("glyph", ["l", "i", "|", "1"])
@pytest.mark.parametrize("gap", [0, 1, 2])
def test_a_typed_glyph_abutting_the_cursor_is_never_erased_with_it(glyph, gap):
    import numpy as np

    image, box = _abutting(glyph, gap)
    blanked, boxes = cursor.blank_cursors(image)
    before, after = np.asarray(image), np.asarray(blanked)
    if boxes:
        assert boxes[0][:3] == box[:3] and boxes[0][3] in (box[3] - 1, box[3])  # the cursor, nothing wider
    outside = np.ones(before.shape[:2], dtype=bool)
    outside[box[1] : box[3], box[0] : box[2]] = False
    if boxes:
        assert (before[outside] == after[outside]).all()  # every pixel but the cursor's own is untouched
    else:
        assert (before == after).all()  # merged with the glyph: nothing blanked, the ink is left to be read


@pytest.mark.parametrize("glyph", ["l", "i", "|", "1"])
@pytest.mark.parametrize("gap", [0, 1, 2])
def test_a_typed_glyph_abutting_the_cursor_is_seen_in_the_picture_whatever_ocr_makes_of_it(glyph, gap):
    """Either merged with the cursor (no block found: the stable-text path) or ink in the cell left of it."""
    image, _ = _abutting(glyph, gap)
    boxes = cursor.find_cursors(image)
    assert not boxes or all(cursor.glyph_before(image, box) for box in boxes)


@pytest.mark.parametrize("name", ["idle-block-cursor-a", "idle-block-cursor-b"])
def test_nothing_is_left_of_the_idle_cursor_in_the_real_screens(name):
    image = Image.open(FIXTURES / f"{name}-2026-10-04.png")
    assert [cursor.glyph_before(image, box) for box in cursor.find_cursors(image)] == [False]


def test_ocr_dropping_a_lone_glyph_against_the_cursor_is_a_visitor_not_a_free_line():
    term = _terminal([(PROMPT, True)])
    term._glyph_against_cursor = True
    with pytest.raises(TerminalBusy, match="a character OCR could not read"):
        term.refuse_if_busy()
