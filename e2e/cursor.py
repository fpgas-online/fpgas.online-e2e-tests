"""Finding the terminal's cursor in a screenshot, so OCR never has to read it.

xterm draws the cursor as a filled block while the terminal has focus and as a
hollow rectangle (a one-pixel outline) when it does not. tesseract reads that
block as whatever it resembles on the day ("[]", "9}", "|"), and any of those
after a prompt looks like a visitor's half-typed text. Rather than list the
readings, the cursor is found in the picture and painted out in the
background colour before OCR runs, so what is left after the prompt is real
glyphs or nothing.

A cursor is a cell-sized shape no character is:

  filled   a solid block: the same run of ink, at least `MIN_CELL_HEIGHT` rows
           tall and wider than a stroke, on every one of its rows. A letter's
           stem is a few pixels wide and its curves change from row to row.
  hollow   a rectangle outline whose inside is empty. "[]" typed side by side
           has a stroke through the middle, so it is not one.

Text under or over a cursor (an inverted character) leaves a shape that is
neither, and is not blanked: it is read, conservatively, as text.
"""

from __future__ import annotations

import numpy as np
from PIL import Image

MIN_CELL_HEIGHT = 14  # the site's default font is 17 px a row; glyph stems reach 13
MAX_CELL_HEIGHT = 40
MIN_CELL_WIDTH = 6  # wider than any stem
INK = 80  # how far from the background a pixel is to count as ink (0-255 grey)

Box = tuple[int, int, int, int]


def _background(array: np.ndarray) -> np.ndarray:
    packed = array[..., 0].astype(np.int64) << 16 | array[..., 1].astype(np.int64) << 8 | array[..., 2]
    values, counts = np.unique(packed, return_counts=True)
    top = int(values[counts.argmax()])
    return np.array([top >> 16, (top >> 8) & 255, top & 255], dtype=np.uint8)


def _is_cell(width: int, height: int) -> bool:
    """One character cell is a good deal taller than wide (the site's is 9 by 17); "[]" typed is two of them wide."""
    return 0.3 * height <= width <= 0.7 * height


def _runs(row: np.ndarray) -> list[tuple[int, int]]:
    """The (start, end) of each run of True in a row, end exclusive."""
    edges = np.flatnonzero(np.diff(np.concatenate(([0], row.astype(np.int8), [0]))))
    return [(int(a), int(b)) for a, b in zip(edges[::2], edges[1::2])]


def find_cursors(image: Image.Image) -> list[Box]:
    """Boxes (left, top, right, bottom; exclusive) of every cursor-shaped thing in a terminal screenshot."""
    array = np.asarray(image.convert("RGB"))
    background = _background(array)
    ink = np.abs(array.astype(np.int16) - background.astype(np.int16)).max(axis=2) > INK
    height = ink.shape[0]
    runs = [_runs(ink[y]) for y in range(height)]
    found: list[Box] = []

    # filled: one run repeated on consecutive rows
    open_runs: dict[tuple[int, int], int] = {}
    for y in range(height + 1):
        here = {r for r in (runs[y] if y < height else []) if r[1] - r[0] >= MIN_CELL_WIDTH}
        for run in list(open_runs):
            if run not in here:
                top = open_runs.pop(run)
                rows = y - top
                if MIN_CELL_HEIGHT <= rows <= MAX_CELL_HEIGHT and _is_cell(run[1] - run[0], rows):
                    found.append((run[0], top, run[1], y))
        for run in here:
            open_runs.setdefault(run, y)

    # hollow: the same run at the top and the bottom, straight sides, nothing inside
    for top in range(height):
        for start, end in runs[top]:
            if end - start < MIN_CELL_WIDTH:
                continue
            for rows in range(MIN_CELL_HEIGHT, min(MAX_CELL_HEIGHT, height - top) + 1):
                bottom = top + rows - 1
                if (start, end) not in runs[bottom] or not _is_cell(end - start, rows):
                    continue
                sides = ink[top : bottom + 1, start].all() and ink[top : bottom + 1, end - 1].all()
                inside = ink[top + 2 : bottom - 1, start + 2 : end - 2]
                if sides and not inside.any():
                    found.append((start, top, end, bottom + 1))
                    break
    return found


def blank_cursors(image: Image.Image) -> tuple[Image.Image, list[Box]]:
    """The screenshot with every cursor painted over in the background colour, and where they were."""
    boxes = find_cursors(image)
    if not boxes:
        return image, []
    array = np.array(image.convert("RGB"))
    background = _background(array)
    for left, top, right, bottom in boxes:
        array[max(top - 1, 0) : bottom + 1, max(left - 1, 0) : right + 1] = background
    return Image.fromarray(array), boxes
