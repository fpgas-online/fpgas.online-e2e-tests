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


def read_clock(image: Image.Image) -> str | None:
    """Read an HH:MM:SS clock, such as the one the Pi burns into the camera picture."""
    match = _CLOCK.search(read_text(image, psm=7, whitelist=CLOCK_WHITELIST))
    return match.group(1) if match else None


def strip_ansi(text: str) -> str:
    """Remove terminal escape sequences, keeping the characters a user sees."""
    return _ANSI.sub("", text)


def normalise(text: str) -> str:
    """Strip terminal escapes and collapse whitespace, so two readings can be compared."""
    return _WHITESPACE.sub(" ", strip_ansi(text)).strip()


def looks_like(a: str, b: str, threshold: float = 0.85) -> bool:
    """True when two strings are the same modulo a few OCR misreadings."""
    return difflib.SequenceMatcher(None, normalise(a), normalise(b)).ratio() >= threshold
