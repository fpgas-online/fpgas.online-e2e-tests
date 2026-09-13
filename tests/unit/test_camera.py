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
