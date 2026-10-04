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


class CameraNotShown(RuntimeError):
    """No player element for this board is on screen; the message says what was found and in what state."""


class Camera:
    """The picture on a board page, whichever player is showing it.

    The page carries two players for one camera (fpgas.online-site
    whep-live.js): a low-latency WHEP <video> inside `.whep-live`, which is
    displayed while its picture is arriving, and the older video.js HLS
    player, which is hidden and paused meanwhile and is what the page falls
    back to when WHEP delivers nothing. Everything the suite reads comes from
    the element that is displayed now, because that is what a person sees; the
    hidden one is in the page but showing nothing.
    """

    def __init__(self, page, video_selector: str, port: int | None = None):
        self.page = page
        self.selector = video_selector
        # The page's own controls are addressed by switch port.
        self.port = port if port is not None else video_selector.rsplit("player", 1)[-1]

    def _candidates(self) -> list[tuple[str, str]]:
        """The elements that can show this board's picture, WHEP first: (what it is, selector)."""
        hls_id = self.selector.lstrip("#")
        whep = f'.whep-live[data-hls-id="{hls_id}"] video'
        # video.js moves the author's id onto a wrapper <div> and renames the
        # media element to "<id>_html5_api", so the obvious selector resolves
        # to a div with no currentTime and no videoWidth. Before the player
        # initialises the id is still on the <video>, hence the fallback.
        inner = f"{self.selector} video"
        videojs = inner if self.page.locator(inner).count() else self.selector
        return [("the WHEP <video>", whep), ("the video.js <video>", videojs)]

    def video_selector(self) -> str:
        """The <video> that is displayed now; raises CameraNotShown, saying what was found, if none is."""
        found = []
        for what, selector in self._candidates():
            locator = self.page.locator(selector)
            if not locator.count():
                found.append(f"{what} ({selector}): not in the page")
            elif locator.is_visible():
                return selector
            else:
                found.append(f"{what} ({selector}): in the page but not visible")
        raise CameraNotShown(f"no camera picture is displayed; found {'; '.join(found)}")

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
        try:
            selector = self.video_selector()
        except CameraNotShown as exc:
            return {"error": str(exc)}
        return self.page.evaluate(
            """
            (selector) => {
              const v = document.querySelector(selector);
              if (!v) return {error: 'no video element'};
              return {
                element: v.closest('.whep-live') ? 'whep' : v.id,
                videoWidth: v.videoWidth, readyState: v.readyState,
                currentTime: Number(v.currentTime.toFixed(1)), paused: v.paused,
                error: v.error ? `${v.error.code}: ${v.error.message}` : null,
                // The board pages play HLS, which Chromium cannot handle
                // natively -- it only works because video.js is fetched from a
                // third-party CDN. If that fetch fails the element just sits at
                // readyState 0 forever with no error, so say whether it loaded.
                videojs: typeof window.videojs,
                src: v.currentSrc || null,
                srcObject: Boolean(v.srcObject),
              };
            }
            """,
            selector,
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
        clock and all. So require a clock that was readable and then stays at
        one readable value for several readings running, and whose pixels did
        not move across those same shots. An unreadable reading is never
        evidence of stopping: it may be OCR failing on a low-contrast overlay,
        a dark player or a page error, and "the board lost power" must not be
        concluded from "the clock could not be read" (the pixels moving or
        not is the audit's way to tell a faint clock that ticks from one that
        stopped, but only once a readable value agrees). A check that only
        ever saw unreadable readings reports that, as a failure of the check.
        Five shots three seconds apart: a player can stall for a few seconds
        on a live feed without the board having gone anywhere.
        """
        deadline = time.monotonic() + timeout
        seen: list[str | None] = []
        run: list[str] = []  # consecutive identical readable readings
        shots: list = []  # the shots behind `run`
        while time.monotonic() < deadline:
            shot = self.shot()
            try:
                reading = ocr.read_clock(crop_fraction(shot, *CLOCK_REGION))
            except Exception:  # noqa: BLE001 - an unreadable picture is a reading too
                reading = None
            seen.append(reading)
            if reading is None:
                run, shots = [], []
            elif run and run[-1] != reading:
                run, shots = [reading], [shot]
            else:
                run.append(reading)
                shots.append(shot)
            if len(run) >= consecutive:
                shots = shots[-consecutive:]
                ticks = [changed_fraction(a, b, region=CLOCK_REGION) for a, b in zip(shots, shots[1:])]
                if all(tick <= TICK for tick in ticks):
                    return True, (
                        f"clock stuck at {run[0]!r} across {consecutive} readable readings {gap}s apart; "
                        f"its pixels did not move"
                    )
            time.sleep(gap)
        readable = [r for r in seen if r is not None]
        if not readable:
            return False, (
                f"the clock was unreadable on all {len(seen)} readings within {timeout}s, "
                "so whether the picture stopped cannot be told"
            )
        unreadable = len(seen) - len(readable)
        return False, (
            f"the picture never stuck at one readable clock value within {timeout}s; "
            f"last readings {seen[-6:]} ({unreadable} of {len(seen)} unreadable)"
        )

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
