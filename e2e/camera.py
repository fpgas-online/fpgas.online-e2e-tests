"""What the camera shows, as the page renders it.

Assertions use screenshots of the <video> element rather than frames drawn out
of the decoder, because a screenshot is what the user sees. The Pi burns a
clock into the picture, so "is this feed live?" is answered by OCRing that
clock twice and checking it advanced -- which a frozen picture cannot fake.

Because the camera runs on the Pi (fpgas-online-cam's cam.service), the feed
going away is itself evidence that the Pi lost power.
"""

from __future__ import annotations

import io
import time

import numpy as np
from PIL import Image

from e2e import ocr

# The Pi draws its clock in the top-left corner; the same fractions
# fpgas.online-cam/tests/measure-latency.mjs uses.
CLOCK_REGION = (0.0, 0.0, 0.30, 0.12)

# Everything below the clock overlay. Use this when asking "did the picture
# change?", because the clock changes every second and would answer yes on its
# own. Deliberately NOT a box around the LEDs: each board's camera is aimed
# differently -- pi2's view is a dark oblique close-up with indicator lights
# scattered across the frame -- so any fixed LED box is wrong somewhere.
PICTURE_REGION = (0.0, 0.15, 1.0, 0.85)


def crop_fraction(image: Image.Image, left: float, top: float, width: float, height: float) -> Image.Image:
    w, h = image.size
    box = (round(left * w), round(top * h), round((left + width) * w), round((top + height) * h))
    return image.crop(box)


def difference(a: Image.Image, b: Image.Image, region: tuple | None = None) -> float:
    """Mean absolute per-channel difference, normalised to 0.0 - 1.0."""
    if region is not None:
        a, b = crop_fraction(a, *region), crop_fraction(b, *region)
    if a.size != b.size:
        b = b.resize(a.size)
    left = np.asarray(a.convert("RGB"), dtype=np.int16)
    right = np.asarray(b.convert("RGB"), dtype=np.int16)
    return float(np.abs(left - right).mean() / 255.0)


def clock_advanced(first: str | None, second: str | None, gap: float) -> bool:
    """True when the second clock reading is a plausible step on from the first.

    Asking only whether the string changed lets OCR noise counterfeit a live
    feed: the reader misreads a leading zero as a 2, so a frozen clock can
    come back as '05:44:25' then '25:44:25' and pass. Requiring a step of
    roughly the sampling gap means a reading has to be both self-consistent
    and moving, which noise does not manage twice in a row.
    """
    if first is None or second is None:
        return False
    try:
        start, end = _seconds(first), _seconds(second)
    except ValueError:
        return False
    step = (end - start) % 86400  # a run can straddle midnight
    return 1 <= step <= gap + 5


def _seconds(clock: str) -> int:
    hours, minutes, seconds = (int(part) for part in clock.split(":"))
    return hours * 3600 + minutes * 60 + seconds


class Camera:
    """The video element on a board page."""

    def __init__(self, page, video_selector: str):
        self.page = page
        self.selector = video_selector

    def video_selector(self) -> str:
        """Where the real <video> lives once video.js has had its way.

        video.js moves the author's id onto a wrapper <div> and renames the
        media element to "<id>_html5_api", so the obvious selector resolves to
        a div with no currentTime and no videoWidth. Before the player
        initialises the id is still on the <video>, hence the fallback.
        """
        inner = f"{self.selector} video"
        return inner if self.page.locator(inner).count() else self.selector

    def shot(self) -> Image.Image:
        """A screenshot of the video element as rendered."""
        return Image.open(io.BytesIO(self.page.locator(self.video_selector()).screenshot()))

    def clock(self) -> str | None:
        """The clock the Pi burns into the picture, or None if it cannot be read."""
        return ocr.read_clock(crop_fraction(self.shot(), *CLOCK_REGION))

    def player_state(self) -> dict:
        """What the <video> element itself reports.

        Worth capturing alongside any camera failure: a stalled feed and a
        player that never started look identical in the picture but are very
        different faults. readyState 0 with no error and paused=True means the
        player never began -- usually the browser's autoplay policy.
        """
        return self.page.evaluate(
            """
            (selector) => {
              const v = document.querySelector(selector);
              if (!v) return {error: 'no video element'};
              return {
                videoWidth: v.videoWidth, readyState: v.readyState,
                currentTime: Number(v.currentTime.toFixed(1)), paused: v.paused,
                error: v.error ? `${v.error.code}: ${v.error.message}` : null,
                // The board pages play HLS, which Chromium cannot handle
                // natively -- it only works because video.js is fetched from a
                // third-party CDN. If that fetch fails the element just sits at
                // readyState 0 forever with no error, so say whether it loaded.
                videojs: typeof window.videojs,
                src: v.currentSrc || null,
              };
            }
            """,
            self.video_selector(),
        )

    def is_live(self, gap: float = 3.0) -> tuple[bool, str]:
        """True when the burned-in clock advanced across two readings `gap` seconds apart."""
        first = self.clock()
        time.sleep(gap)
        second = self.clock()
        live = clock_advanced(first, second, gap)
        detail = f"clock {first!r} -> {second!r}"
        if not live:
            detail = f"{detail}; player {self.player_state()}"
            if first is None:
                # Distinguish "no clock in the picture" from "OCR misread it".
                raw = ocr.read_clock_debug(crop_fraction(self.shot(), *CLOCK_REGION))
                detail = f"{detail}; ocr read {raw!r}"
        return live, detail

    def check_live(self, timeout: float, gap: float = 3.0) -> tuple[bool, str]:
        """Did the picture come alive within the timeout? Reports, never raises.

        For assertions, so the evidence log records what was actually seen.
        wait_until_live raises instead, which suits a precondition but makes
        any evidence entry built on it a constant.
        """
        try:
            return True, self._wait(True, timeout, gap)
        except TimeoutError as exc:
            return False, str(exc)

    def check_not_live(self, timeout: float, gap: float = 3.0) -> tuple[bool, str]:
        """Did the picture stop advancing within the timeout? Reports, never raises."""
        try:
            return True, self._wait(False, timeout, gap)
        except TimeoutError as exc:
            return False, str(exc)

    def wait_until_live(self, timeout: float, gap: float = 3.0) -> str:
        """Block until the feed is live. Returns the detail string; raises on timeout."""
        return self._wait(True, timeout, gap)

    def wait_until_not_live(self, timeout: float, gap: float = 3.0) -> str:
        """Block until the feed stops advancing -- i.e. the Pi stopped sending."""
        return self._wait(False, timeout, gap)

    def _wait(self, want_live: bool, timeout: float, gap: float) -> str:
        deadline = time.monotonic() + timeout
        detail = "never sampled"
        while time.monotonic() < deadline:
            try:
                live, detail = self.is_live(gap=gap)
            except Exception as exc:  # noqa: BLE001 - a dead player raises in many ways
                live, detail = False, f"could not read the picture: {exc}"
            if live == want_live:
                return detail
        state = "live" if want_live else "not live"
        raise TimeoutError(f"camera did not become {state} within {timeout}s ({detail})")
