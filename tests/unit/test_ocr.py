from PIL import Image, ImageDraw, ImageFont

from e2e import ocr


def _render(text: str, size=(420, 60), fontsize=32) -> Image.Image:
    """White-on-black monospace, like a terminal or the camera's clock overlay."""
    img = Image.new("RGB", size, "black")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", fontsize)
    except OSError:
        font = ImageFont.load_default()
    draw.text((6, 6), text, fill="white", font=font)
    return img


def test_read_text_reads_a_rendered_line():
    assert "hello world" in ocr.read_text(_render("hello world")).lower()


def test_read_clock_reads_a_timestamp():
    assert ocr.read_clock(_render("12:34:56")) == "12:34:56"


def test_read_clock_returns_none_when_there_is_no_clock():
    assert ocr.read_clock(_render("no clock here")) is None


def test_read_clock_copes_with_a_small_crop():
    """The real clock crop is about 138x50 with ~20px digits.

    The video element renders at roughly 460px wide inside the board page, and
    the clock occupies the top-left 30% x 12% of it, so the crop handed to
    tesseract is small. Reading it needs upscaling, not a bigger font on the
    page -- the page is rendering at its normal size and a person can read it.
    """
    small = _render("12:34:56", size=(138, 50), fontsize=20)
    assert ocr.read_clock(small) == "12:34:56"


def test_normalise_collapses_whitespace_and_strips():
    assert ocr.normalise("  a \t b\n\n c  ") == "a b c"


def test_normalise_removes_ansi_escape_sequences():
    assert ocr.normalise("\x1b[32mgreen\x1b[0m text") == "green text"


def test_strip_ansi_keeps_the_characters_a_user_sees():
    assert ocr.strip_ansi("\x1b[0;32mpi@host\x1b[0m:~ $ ") == "pi@host:~ $ "


def test_looks_like_tolerates_a_few_ocr_errors():
    assert ocr.looks_like("total 2192119 top.bit", "total 2l92ll9 top.bit")


def test_looks_like_rejects_different_text():
    assert not ocr.looks_like("permission denied", "total 2192119 top.bit")
