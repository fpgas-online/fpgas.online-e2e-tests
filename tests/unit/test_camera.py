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


class _FakeClock:
    """A camera whose clock returns a scripted sequence of readings."""

    def __init__(self, readings):
        self.readings = list(readings)
        self.last = readings[-1]

    def clock(self):
        """Never runs out: a fake that returned one sentinel forever once
        exhausted would itself look exactly like a stuck picture."""
        if self.readings:
            self.last = self.readings.pop(0)
            return self.last
        if self.last is None:
            return None
        h, m, s = (int(part) for part in self.last.split(":"))
        total = (h * 3600 + m * 60 + s + 3) % 86400
        self.last = f"{total // 3600:02d}:{total // 60 % 60:02d}:{total % 60:02d}"
        return self.last

    def check_stopped(self, *a, **k):
        return camera.Camera.check_stopped(self, *a, **k)


def test_check_stopped_does_not_fire_on_a_player_seeking_in_its_buffer():
    """Measured on welland pi37: '15:59:01' -> '15:59:45' -> '15:59:13'.

    A stalled player that jumps to the live edge is not a board that lost
    power, but every one of those steps is "not advancing plausibly".
    """
    cam = _FakeClock(["15:59:01", "15:59:45", "15:59:13", "15:59:16", "15:59:19"])
    stopped, detail = cam.check_stopped(timeout=1.0, gap=0.0)
    assert not stopped, detail


def test_check_stopped_fires_on_a_picture_that_really_sticks():
    cam = _FakeClock(["15:59:01", "15:59:04", "15:59:07", "15:59:07"])
    cam.readings.extend(["15:59:07"] * 50)
    stopped, detail = cam.check_stopped(timeout=1.0, gap=0.0)
    assert stopped
    assert "stuck at '15:59:07'" in detail


def test_check_stopped_fires_when_the_picture_goes_dark():
    cam = _FakeClock(["15:59:01", None, None, None, None])
    stopped, detail = cam.check_stopped(timeout=1.0, gap=0.0)
    assert stopped
    assert "no clock readable" in detail


def test_changed_fraction_counts_pixels_not_brightness():
    """A small LED in a big dark frame: the mean is nothing, the count is not."""
    fraction = camera.changed_fraction(_with_led("black"), _with_led("red"))
    assert abs(fraction - (111 * 26) / (320 * 200)) < 0.001


def test_changed_fraction_ignores_compression_noise():
    noisy = _solid((10, 10, 10))
    assert camera.changed_fraction(_solid("black"), noisy) == 0.0
