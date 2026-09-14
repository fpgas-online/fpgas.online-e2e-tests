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

# How much of the clock region has to change between two shots for the clock
# to count as ticking. Measured 2026-09-14 in real Chrome: a live feed moves
# 0.4% to 1.7% of it every 1.5s (welland p33, p37 -- the faintest clocks on
# the site); a player that never started, and a stream that is gone, move
# 0.000% of it even while an error overlay animates elsewhere in the frame.
TICK = 0.001

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


def changed_fraction(a: Image.Image, b: Image.Image, region: tuple | None = None, tolerance: int = 40) -> float:
    """The fraction of pixels that changed noticeably between two shots, 0.0 - 1.0.

    A mean difference over the frame cannot see an LED: a few hundred bright
    pixels among a million dark ones move the mean by nothing. Counting the
    pixels that moved by more than a person would notice does see it, and
    reads the same however small the LED is in the frame. `tolerance` is the
    per-channel step that counts as a change; video compression noise sits
    well below it.
    """
    if region is not None:
        a, b = crop_fraction(a, *region), crop_fraction(b, *region)
    if a.size != b.size:
        b = b.resize(a.size)
    left = np.asarray(a.convert("RGB"), dtype=np.int16)
    right = np.asarray(b.convert("RGB"), dtype=np.int16)
    moved = np.abs(left - right).max(axis=2) > tolerance
    return float(moved.mean())


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

    def __init__(self, page, video_selector: str, port: int | None = None):
        self.page = page
        self.selector = video_selector
        # The page's own controls are addressed by switch port.
        self.port = port if port is not None else video_selector.rsplit("player", 1)[-1]

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
        """True when the burned-in clock is ticking across `gap` seconds.

        What a person sees is the clock's digits changing every second, and
        that is what is measured: the fraction of the clock's pixels that
        moved between shots, in each of two halves of the gap. Reading the
        digits is a separate matter -- the clock on welland's p33 and p37 is
        grey on magenta and OCR returns rubbish for it while the picture is
        plainly live, which is how two live cameras were once reported dead.
        The digits go into the detail when they can be read, and a readable
        clock that stands still while the pixels move is reported too.
        """
        shots = [self.shot()]
        for _ in range(2):
            time.sleep(gap / 2)
            shots.append(self.shot())
        ticks = [changed_fraction(a, b, region=CLOCK_REGION) for a, b in zip(shots, shots[1:])]
        live = all(tick > TICK for tick in ticks)
        first, second = (ocr.read_clock(crop_fraction(s, *CLOCK_REGION)) for s in (shots[0], shots[-1]))
        moved = ", ".join(f"{tick:.2%}" for tick in ticks)
        detail = f"clock {first!r} -> {second!r} (clock pixels moved {moved})"
        if live and first is not None and second is not None and not clock_advanced(first, second, gap):
            detail = f"{detail}; the digits read did not advance plausibly, so one reading is a misread"
        if not live:
            detail = f"{detail}; player {self.player_state()}"
        return live, detail

    def wait_for_change(
        self, before: Image.Image, threshold: float, timeout: float, gap: float = 2.0, region: tuple = PICTURE_REGION
    ) -> tuple[bool, str]:
        """Watch until the picture differs from `before`, or give up.

        The feed runs about a minute behind the board, so a shot taken the
        moment the FPGA is programmed still shows the old design. A person
        keeps looking at the camera until the LEDs change; so does this.
        """
        deadline = time.monotonic() + timeout
        peak = 0.0
        while time.monotonic() < deadline:
            fraction = changed_fraction(before, self.shot(), region=region)
            peak = max(peak, fraction)
            if fraction > threshold:
                return True, f"{fraction:.4%} of the picture changed (threshold {threshold:.2%})"
            time.sleep(gap)
        return False, f"at most {peak:.4%} of the picture changed within {timeout}s (threshold {threshold:.2%})"

    def keeps_changing(
        self, threshold: float, gap: float = 2.0, pairs: int = 5, region: tuple = PICTURE_REGION
    ) -> tuple[bool, str]:
        """Does the picture keep moving? A design that is running keeps the LEDs moving.

        Several pairs of shots, not one: a counter's LEDs can land on the same
        pattern in two shots two seconds apart (measured on ps1 pi7: about one
        pair in ten was identical while the counter ran), and one still pair
        is not a frozen design.
        """
        seen = []
        previous = self.shot()
        for _ in range(pairs):
            time.sleep(gap)
            current = self.shot()
            seen.append(changed_fraction(previous, current, region=region))
            previous = current
            if seen[-1] > threshold:
                break
        moved = max(seen)
        readings = ", ".join(f"{s:.4%}" for s in seen)
        return moved > threshold, f"consecutive shots {gap}s apart differed by {readings} (threshold {threshold:.2%})"

    def reset_player(self) -> None:
        """Click the page's own "reset video player" button, as a person would."""
        self.page.click(f"#refresh-video-player{self.port}")

    def press_play_if_offered(self) -> bool:
        """If the player is showing its big Play button, press it, as a person would."""
        button = self.page.locator(f"{self.selector} .vjs-big-play-button")
        if not button.is_visible():
            return False
        button.click()
        return True

    def check_live_with_recovery(self, timeout: float, gap: float = 3.0) -> tuple[bool, str]:
        """Wait for the picture, and if it does not come, do what a person does.

        A player that never started looks exactly like a dead camera: black,
        readyState 0. What a person sees is either the player's own Play
        button, which they press, or a black pane, for which the page offers
        "reset video player". Both are tried, in that order. The detail says
        what was needed, because a picture that only comes after a press is
        itself a finding: measured on ps1 pi9 on 2026-09-14, three loads in
        four showed the Play button, and pressing it did nothing.
        """
        live, detail = self.check_live(timeout, gap=gap)
        if live:
            return True, detail
        if self.press_play_if_offered():
            live, after = self.check_live(timeout, gap=gap)
            if live:
                return True, f"the picture needed the player's Play button: {detail} -> {after}"
            detail = f"{detail}; pressing the player's Play button did not help ({after})"
        self.reset_player()
        live, after = self.check_live(timeout, gap=gap)
        return live, f"the picture needed the page's 'reset video player' button: {detail} -> {after}"

    def check_stopped(self, timeout: float, gap: float = 3.0, consecutive: int = 5) -> tuple[bool, str]:
        """Wait until the picture is genuinely stuck, not merely discontinuous.

        "Not advancing plausibly" is too weak to mean "the board lost power".
        A player that stalls and then seeks to the live edge reports a large
        forward jump, and one recovering from a stall can even read backwards
        -- measured on welland pi37: '15:59:01' -> '15:59:45' -> '15:59:13'.
        None of that is a picture that stopped; it is a picture skipping
        about, which is what a buffer does, not what a dead board does.

        What a person sees when the power goes is a frame that sits there,
        clock and all. So require the clock's pixels not to move across
        several shots running -- which also covers the dark player, where
        there is no clock -- before saying it stopped. Five shots three
        seconds apart: a player can stall for a few seconds on a live feed
        without the board having gone anywhere.
        """
        deadline = time.monotonic() + timeout
        shots: list = []
        readings: list[str | None] = []
        while time.monotonic() < deadline:
            shots.append(self.shot())
            shots = shots[-consecutive:]
            if len(shots) == consecutive:
                ticks = [changed_fraction(a, b, region=CLOCK_REGION) for a, b in zip(shots, shots[1:])]
                if all(tick <= TICK for tick in ticks):
                    clock = ocr.read_clock(crop_fraction(shots[-1], *CLOCK_REGION))
                    stuck = "no clock readable" if clock is None else f"clock stuck at {clock!r}"
                    return True, f"{stuck}; its pixels did not move across {consecutive} shots {gap}s apart"
            readings.append(ocr.read_clock(crop_fraction(shots[-1], *CLOCK_REGION)))
            time.sleep(gap)
        return False, f"the picture never stuck within {timeout}s; last readings {readings[-consecutive:]}"

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
