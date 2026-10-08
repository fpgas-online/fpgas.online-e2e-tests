import pytest
from PIL import Image, ImageDraw

from e2e import camera
from e2e.camera import CameraNotShown, clock_advanced


def _solid(colour, size=(320, 200)):
    return Image.new("RGB", size, colour)


def _with_led(colour, size=(320, 200)):
    img = Image.new("RGB", size, "black")
    ImageDraw.Draw(img).rectangle([10, 170, 120, 195], fill=colour)
    return img


def test_identical_images_have_zero_difference():
    assert camera.difference(_solid("black"), _solid("black")) == 0.0


def test_black_and_white_are_maximally_different():
    assert camera.difference(_solid("black"), _solid("white")) > 0.99


def test_a_small_change_is_a_small_whole_image_difference():
    assert 0.0 < camera.difference(_with_led("black"), _with_led("red")) < 0.2


def test_restricting_to_the_led_region_amplifies_that_same_change():
    led = (0.0, 0.8, 0.45, 0.2)
    whole = camera.difference(_with_led("black"), _with_led("red"))
    region = camera.difference(_with_led("black"), _with_led("red"), region=led)
    assert region > whole * 3


def test_crop_fraction_takes_fractions_of_the_image():
    cropped = camera.crop_fraction(_solid("black", (400, 200)), 0.0, 0.0, 0.5, 0.25)
    assert cropped.size == (200, 50)


def test_images_of_different_sizes_are_compared_after_resizing():
    assert camera.difference(_solid("black", (320, 200)), _solid("black", (640, 400))) == 0.0


def test_clock_advanced_accepts_a_plausible_step():
    assert clock_advanced("05:44:25", "05:44:28", gap=3.0)


def test_clock_advanced_rejects_a_frozen_clock():
    assert not clock_advanced("05:44:25", "05:44:25", gap=3.0)


def test_clock_advanced_rejects_two_misreadings_of_the_same_frozen_clock():
    """OCR misreads the leading digit: '05:50:42' comes back as '25:50:42'.

    Asking only "did the string change?" lets noise counterfeit a live feed,
    which is the one thing this assertion exists to prove.
    """
    assert not clock_advanced("05:44:25", "25:44:25", gap=3.0)


def test_clock_advanced_rejects_time_running_backwards():
    assert not clock_advanced("05:44:28", "05:44:25", gap=3.0)


def test_clock_advanced_copes_with_midnight():
    assert clock_advanced("23:59:59", "0:00:02", gap=3.0)


def test_clock_advanced_needs_both_readings():
    assert not clock_advanced(None, "05:44:28", gap=3.0)
    assert not clock_advanced("05:44:25", None, gap=3.0)


def _frame(clock_step: int | None, size=(320, 200)):
    """A picture with a fake 'clock' in the clock region: a block whose
    position encodes the time, or nothing at all for a dark player."""
    img = Image.new("RGB", size, "black")
    if clock_step is not None:
        x = 4 + (clock_step % 20) * 3
        ImageDraw.Draw(img).rectangle([x, 4, x + 12, 16], fill="white")
    return img


class _FakeCamera:
    """A camera whose shots follow a script, then keep going in the same spirit.

    A fake that ran out and returned one frame forever would itself look
    exactly like a stuck picture, so after the script the clock keeps
    ticking (`then="ticking"`) or stays put (`then="stuck"`).
    """

    def __init__(self, steps, then="ticking"):
        self.steps = list(steps)
        self.then = then
        self.last = steps[-1]

    def shot(self):
        if self.steps:
            self.last = self.steps.pop(0)
        elif self.then == "ticking" and self.last is not None:
            self.last += 1
        return _frame(self.last)

    def shot_with_selector(self):
        return self.shot(), "#video-player1 video"

    def check_stopped(self, *a, **k):
        return camera.Camera.check_stopped(self, *a, **k)


def test_check_stopped_does_not_fire_on_a_player_seeking_in_its_buffer(monkeypatch):
    """Measured on welland pi37: '15:59:01' -> '15:59:45' -> '15:59:13'.

    A stalled player that jumps to the live edge is not a board that lost
    power: the clock's pixels keep moving, however implausibly the digits
    read.
    """
    monkeypatch.setattr(camera.ocr, "read_clock", lambda _img: None)
    cam = _FakeCamera([1, 45, 13, 16, 19], then="ticking")
    stopped, detail = cam.check_stopped(timeout=0.5, gap=0.0)
    assert not stopped, detail


def test_check_stopped_fires_on_a_picture_that_really_sticks(monkeypatch):
    monkeypatch.setattr(camera.ocr, "read_clock", lambda _img: "15:59:07")
    cam = _FakeCamera([1, 4, 7, 7, 7, 7, 7, 7], then="stuck")
    stopped, detail = cam.check_stopped(timeout=1.0, gap=0.0)
    assert stopped
    assert "stuck at '15:59:07'" in detail
    assert "did not move" in detail


def test_check_stopped_does_not_fire_on_a_faint_clock_that_ocr_cannot_read(monkeypatch):
    """welland p33/p37: the digits are unreadable but plainly ticking."""
    monkeypatch.setattr(camera.ocr, "read_clock", lambda _img: None)
    cam = _FakeCamera([1, 2, 3, 4, 5, 6], then="ticking")
    stopped, _ = cam.check_stopped(timeout=0.3, gap=0.0)
    assert not stopped


def test_changed_fraction_counts_pixels_not_brightness():
    """A small LED in a big dark frame: the mean is nothing, the count is not."""
    fraction = camera.changed_fraction(_with_led("black"), _with_led("red"))
    assert abs(fraction - (111 * 26) / (320 * 200)) < 0.001


def test_changed_fraction_ignores_compression_noise():
    noisy = _solid((10, 10, 10))
    assert camera.changed_fraction(_solid("black"), noisy) == 0.0


def _scripted_reads(monkeypatch, readings, then=None):
    """Make OCR return `readings` in turn, then `then` (a repeated reading) forever."""
    queue = list(readings)
    monkeypatch.setattr(camera.ocr, "read_clock", lambda _img: queue.pop(0) if queue else then)


def test_check_stopped_does_not_take_an_unreadable_picture_as_evidence_of_stopping(monkeypatch):
    """Five Nones are five failures to read the overlay, not a board that lost power.

    The pixels do not move here either (a dark player), which is exactly the
    case that must still not be called stopped.
    """
    _scripted_reads(monkeypatch, [], then=None)
    cam = _FakeCamera([None] * 5, then="stuck")
    stopped, detail = cam.check_stopped(timeout=1.0, gap=0.0)
    assert not stopped
    assert "unreadable" in detail


def test_check_stopped_does_not_take_a_clock_that_goes_unreadable_as_stopped(monkeypatch):
    _scripted_reads(monkeypatch, ["15:59:01"], then=None)
    cam = _FakeCamera([1, None, None, None, None], then="stuck")
    stopped, detail = cam.check_stopped(timeout=1.0, gap=0.0)
    assert not stopped
    assert "unreadable" in detail


def test_check_stopped_does_not_fire_on_an_advancing_clock(monkeypatch):
    seconds = iter(range(1000))
    monkeypatch.setattr(camera.ocr, "read_clock", lambda _img: f"15:59:{next(seconds) % 60:02d}")
    cam = _FakeCamera([1, 2], then="ticking")
    stopped, detail = cam.check_stopped(timeout=0.3, gap=0.0)
    assert not stopped, detail


def test_check_stopped_needs_the_pixels_still_as_well_as_the_digits(monkeypatch):
    """One misread digit string repeated over a clock that is plainly ticking is not a stopped board."""
    monkeypatch.setattr(camera.ocr, "read_clock", lambda _img: "15:59:07")
    cam = _FakeCamera([1, 2, 3, 4, 5, 6], then="ticking")
    stopped, detail = cam.check_stopped(timeout=0.3, gap=0.0)
    assert not stopped, detail


def test_check_stopped_does_not_fire_when_readable_and_unreadable_readings_alternate(monkeypatch):
    """Frozen pixels, but every second reading is unreadable.

    Unreadable readings must reset the run, not be skipped over: otherwise the
    readable ones would add up to a run of identical readings and call a
    picture stopped that was never once read twice in a row.
    """
    readings = iter(["15:59:07", None] * 50)
    monkeypatch.setattr(camera.ocr, "read_clock", lambda _img: next(readings))
    cam = _FakeCamera([7] * 20, then="stuck")
    stopped, detail = cam.check_stopped(timeout=0.5, gap=0.0)
    assert not stopped, detail


# --- the displayed player can change while a check is comparing shots ---

WHEP = '.whep-live[data-hls-id="video-player1"] video'
HLS = "#video-player1 video"


class _SwitchingCamera(camera.Camera):
    """A Camera whose shots, and the player each came from, follow a script; nothing touches a page."""

    def __init__(self, script):
        self.script = list(script)
        self.last = script[-1]

    def shot_with_selector(self):
        if self.script:
            self.last = self.script.pop(0)
        item = self.last
        if isinstance(item, Exception):
            raise item
        image, selector = item
        return image, selector

    def player_state(self):
        return {}


def _picture(colour, selector):
    return _solid(colour), selector


def test_wait_for_change_fails_loudly_when_the_player_switched_after_the_baseline(monkeypatch):
    """The baseline predates the action, so it cannot be retaken, and white-on-WHEP vs black-on-HLS is no change."""
    monkeypatch.setattr(camera.time, "sleep", lambda _s: None)
    cam = _SwitchingCamera([_picture("white", HLS)])
    with pytest.raises(camera.PlayerSwitched, match="player switched mid-check"):
        cam.wait_for_change(_solid("black"), WHEP, threshold=0.01, timeout=5, gap=0.0)


def test_wait_for_change_still_sees_a_real_change_on_the_same_player(monkeypatch):
    monkeypatch.setattr(camera.time, "sleep", lambda _s: None)
    cam = _SwitchingCamera([_picture("white", WHEP)])
    changed, _ = cam.wait_for_change(_solid("black"), WHEP, threshold=0.01, timeout=5, gap=0.0)
    assert changed


def test_keeps_changing_does_not_count_a_player_switch_as_a_moving_picture(monkeypatch):
    """One switch: the baseline is retaken from the new player; a still picture on it is still still."""
    monkeypatch.setattr(camera.time, "sleep", lambda _s: None)
    cam = _SwitchingCamera([_picture("black", WHEP)] + [_picture("white", HLS)] * 6)
    moving, detail = cam.keeps_changing(threshold=0.01, gap=0.0, pairs=5)
    assert not moving
    assert "0.0000%" in detail


def test_keeps_changing_fails_when_the_player_keeps_switching(monkeypatch):
    monkeypatch.setattr(camera.time, "sleep", lambda _s: None)
    cam = _SwitchingCamera([_picture("black", WHEP), _picture("white", HLS), _picture("black", WHEP)])
    with pytest.raises(camera.PlayerSwitched):
        cam.keeps_changing(threshold=0.01, gap=0.0, pairs=5)


def test_is_live_retakes_its_shots_once_after_a_switch(monkeypatch):
    monkeypatch.setattr(camera.time, "sleep", lambda _s: None)
    monkeypatch.setattr(camera.ocr, "read_clock", lambda _img: None)
    shots = [(_frame(n), WHEP if n else HLS) for n in range(6)]
    live, _ = _SwitchingCamera(shots).is_live(gap=0.0)
    assert live


def test_is_live_fails_when_the_player_switches_twice(monkeypatch):
    monkeypatch.setattr(camera.time, "sleep", lambda _s: None)
    shots = [(_frame(n), WHEP if n % 2 else HLS) for n in range(6)]
    with pytest.raises(camera.PlayerSwitched):
        _SwitchingCamera(shots).is_live(gap=0.0)


def test_a_player_that_is_not_displayed_is_not_a_stopped_camera():
    """check_not_live must not read 'nothing displayed' as 'the board stopped sending video'."""
    cam = _SwitchingCamera([CameraNotShown("no camera picture is displayed; found ...")])
    with pytest.raises(CameraNotShown):
        cam.check_not_live(timeout=1, gap=0.0)


def test_a_player_that_is_not_displayed_is_not_a_live_camera_either():
    cam = _SwitchingCamera([CameraNotShown("no camera picture is displayed; found ...")])
    live, detail = cam.check_live(timeout=0.05, gap=0.0)
    assert not live and "no camera picture is displayed" in detail


def test_check_stopped_does_not_join_shots_of_two_players_into_one_stuck_run(monkeypatch):
    monkeypatch.setattr(camera.ocr, "read_clock", lambda _img: "15:59:07")
    still = _frame(1)
    cam = _SwitchingCamera([(still, WHEP), (still, HLS)] * 5000)
    stopped, _ = cam.check_stopped(timeout=0.3, gap=0.0, consecutive=3)
    assert not stopped


# -- the camera journey on boards with and without a camera -------------------------------------------------------


class _Session:
    def __init__(self, board, live, detail="clock did not advance"):
        self.board = board
        self.camera = _SlowOrLiveCamera(live, detail)


class _SlowOrLiveCamera:
    def __init__(self, live, detail):
        self.live, self.detail, self.calls = live, detail, 0

    def check_live_with_recovery(self, timeout=60.0):
        self.calls += 1
        return self.live, self.detail

    def player_state(self):
        return "readyState 0"


def test_a_camera_less_board_reports_no_camera_and_never_touches_the_player():
    from e2e import journeys
    from e2e.board import Board
    from e2e.evidence import EvidenceLog

    session = _Session(Board("pi-sw2-p43", 43, "Fomu", has_camera=False), live=False)
    log = EvidenceLog()
    journeys.camera_is_live(session, log)  # no AssertionError
    assert session.camera.calls == 0
    assert log.failures == []
    assert "no camera on this board" in log.summary()


def test_a_camera_that_never_goes_live_on_a_board_that_has_one_is_a_failure():
    from e2e import journeys
    from e2e.board import Board
    from e2e.evidence import EvidenceLog

    session = _Session(Board("acorn-sycamore", 44, "Acorn", has_camera=True), live=False)
    with pytest.raises(AssertionError, match="camera is showing a live picture"):
        journeys.camera_is_live(session, EvidenceLog())
    assert session.camera.calls == 1


def test_a_board_whose_camera_the_site_does_not_say_is_checked_like_one_that_has_one():
    from e2e import journeys
    from e2e.board import Board
    from e2e.evidence import EvidenceLog

    session = _Session(Board("pi2", 2, ""), live=False)
    with pytest.raises(AssertionError):
        journeys.camera_is_live(session, EvidenceLog())
