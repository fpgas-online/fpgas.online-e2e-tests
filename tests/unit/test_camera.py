from PIL import Image, ImageDraw

from e2e import camera
from e2e.camera import clock_advanced


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


def test_check_stopped_fires_when_the_picture_goes_dark(monkeypatch):
    monkeypatch.setattr(camera.ocr, "read_clock", lambda _img: None)
    cam = _FakeCamera([1, None, None, None, None, None], then="stuck")
    stopped, detail = cam.check_stopped(timeout=1.0, gap=0.0)
    assert stopped
    assert "no clock readable" in detail


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
