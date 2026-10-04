"""Reading text out of pictures, and comparing text that came from a picture.

OCR is how the suite checks that what the *user* sees matches what the server
sent. It deliberately runs against the site's default rendering: if tesseract
cannot read the terminal at the size and contrast the site ships, a human is
probably struggling too, and that is a finding rather than something to work
around by passing WebSSH its font options.
"""

from __future__ import annotations

import difflib
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image

CLOCK_WHITELIST = "0123456789:"
SCRATCH = Path(__file__).resolve().parents[1] / "tmp"

_CLOCK = re.compile(r"\b([0-2]?\d:[0-5]\d:[0-5]\d)\b")
_ANSI = re.compile(
    r"\x1b\[[0-9;?]*[ -/]*[@-~]"           # CSI sequences
    r"|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)"  # OSC sequences
    r"|\x1b[()][B0]"                       # charset selection
    r"|\x1b[=>]"                           # keypad mode
    r"|[\x0e\x0f]"                          # shift out / shift in, which tmux sprinkles through the prompt
)
_WHITESPACE = re.compile(r"\s+")


class OcrUnavailable(RuntimeError):
    pass


def read_text(image: Image.Image, *, psm: int = 6, whitelist: str | None = None) -> str:
    """Run tesseract over an image and return what it read."""
    if shutil.which("tesseract") is None:
        raise OcrUnavailable("tesseract is not installed; apt install tesseract-ocr tesseract-ocr-eng")
    SCRATCH.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=SCRATCH) as scratch:
        path = Path(scratch) / "ocr.png"
        image.save(path)
        cmd = ["tesseract", str(path), "-", "--psm", str(psm)]
        if whitelist:
            cmd += ["-c", f"tessedit_char_whitelist={whitelist}"]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise OcrUnavailable(f"tesseract failed ({proc.returncode}): {proc.stderr.strip()}")
    return proc.stdout


def _clock_readings(image: Image.Image, upscale: int):
    """The ways to show tesseract a clock, cheapest first.

    The Pi burns its clock over whatever the camera sees. On a dark picture
    that is white on near-black and reads straight off. On an overexposed one
    -- welland's pi37, say -- it is light grey on mid grey, which a person
    reads at a glance and which plain tesseract returns nothing at all for.
    Thresholding and inverting gives it the black-on-white it is happiest
    with, and psm 11 (sparse text) finds the digits when psm 7 sees no single
    line to read.

    This is preprocessing of a screenshot, not a change to how the site
    renders: the page is at its normal size and the clock is plainly legible.
    """
    big = image.resize((image.width * upscale, image.height * upscale), Image.LANCZOS) if upscale > 1 else image
    yield big, 7
    grey = big.convert("L")
    for cut in (200, 160):
        yield grey.point(lambda v, c=cut: 0 if v > c else 255), 11


def read_clock(image: Image.Image, upscale: int = 3) -> str | None:
    """Read an HH:MM:SS clock, such as the one the Pi burns into the camera picture."""
    for candidate, psm in _clock_readings(image, upscale):
        match = _CLOCK.search(read_text(candidate, psm=psm, whitelist=CLOCK_WHITELIST))
        if match:
            return match.group(1)
    return None


def read_clock_debug(image: Image.Image, upscale: int = 3) -> str:
    """What tesseract saw on each attempt, for when read_clock returns None."""
    seen = [
        f"psm{psm}: {read_text(candidate, psm=psm, whitelist=CLOCK_WHITELIST).strip()!r}"
        for candidate, psm in _clock_readings(image, upscale)
    ]
    return "; ".join(seen)


def strip_ansi(text: str) -> str:
    """Remove terminal escape sequences, keeping the characters a user sees."""
    return _ANSI.sub("", text)


def normalise(text: str) -> str:
    """Strip terminal escapes and collapse whitespace, so two readings can be compared."""
    return _WHITESPACE.sub(" ", strip_ansi(text)).strip()


def looks_like(a: str, b: str, threshold: float = 0.85) -> bool:
    """True when two strings are the same modulo a few OCR misreadings."""
    return difflib.SequenceMatcher(None, normalise(a), normalise(b)).ratio() >= threshold
