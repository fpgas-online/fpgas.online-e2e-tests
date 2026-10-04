"""Camera must find the real <video>, not video.js's wrapper.

video.js moves the id from the <video> onto a wrapper <div> and renames the
element to "<id>_html5_api". Verified on ps1.fpgas.online 2026-09-12:

    #video-player2        -> DIV.video-js ...      (currentTime undefined)
    #video-player2 video  -> VIDEO#video-player2_html5_api  (currentTime number)

So the selector the page author wrote resolves to something with no media
properties at all once the player has initialised.
"""

import io
from html.parser import HTMLParser
from pathlib import Path

import pytest
from PIL import Image

from e2e.camera import Camera, CameraNotShown


class FakeLocator:
    def __init__(self, count, visible=True):
        self._count = count
        self._visible = visible

    def count(self):
        return self._count

    def is_visible(self):
        return self._visible


class FakePage:
    """Records what was asked for; reports which selectors exist."""

    def __init__(self, existing, hidden=()):
        self.existing = existing
        self.hidden = set(hidden)
        self.evaluated = []

    def locator(self, selector):
        return FakeLocator(1 if selector in self.existing else 0, visible=selector not in self.hidden)

    def evaluate(self, script, arg=None):
        self.evaluated.append(arg)
        return {}


def test_prefers_the_inner_video_when_videojs_has_wrapped_it():
    page = FakePage({"#video-player2", "#video-player2 video"})
    Camera(page, "#video-player2").player_state()
    assert page.evaluated == ["#video-player2 video"]


def test_falls_back_to_the_given_selector_before_videojs_initialises():
    page = FakePage({"#video-player2"})
    Camera(page, "#video-player2").player_state()
    assert page.evaluated == ["#video-player2"]


# The board page of 2026-10-04 (fixtures/html), which has the WHEP player in front of the video.js one.
BOARD_PAGE = Path(__file__).parents[2] / "fixtures" / "html" / "welland-board-page-2026-10-04.html"
WHEP = '.whep-live[data-hls-id="video-player46"] video'
VIDEOJS = "#video-player46 video"


class _Elements(HTMLParser):
    """The id of each <video> and the data-hls-id of each .whep-live wrapper, as the page's HTML says."""

    def __init__(self):
        super().__init__()
        self.video_ids, self.whep_hls_ids = [], []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "video":
            self.video_ids.append(attrs.get("id"))
        if tag == "div" and "whep-live" in (attrs.get("class") or "").split():
            self.whep_hls_ids.append(attrs.get("data-hls-id"))


def test_the_selectors_match_the_board_page_markup():
    """The WHEP wrapper points at the video.js element by id, which is what the camera looks for."""
    page = _Elements()
    page.feed(BOARD_PAGE.read_text())
    assert page.whep_hls_ids == ["video-player46"]
    assert "video-player46" in page.video_ids
    camera = Camera(FakePage(set()), "#video-player46")
    assert [selector for _, selector in camera._candidates()] == [WHEP, "#video-player46"]


def test_reads_the_whep_video_when_it_is_showing_and_videojs_is_hidden():
    """The failure of issue 7: video.js's element is in the page but hidden while WHEP shows."""
    page = FakePage({WHEP, VIDEOJS}, hidden={VIDEOJS})
    camera = Camera(page, "#video-player46")
    assert camera.video_selector() == WHEP
    camera.player_state()
    assert page.evaluated == [WHEP]


def test_reads_the_videojs_video_when_the_page_has_fallen_back_to_hls():
    page = FakePage({WHEP, VIDEOJS}, hidden={WHEP})
    camera = Camera(page, "#video-player46")
    assert camera.video_selector() == VIDEOJS


def test_reads_the_videojs_video_when_there_is_no_whep_player_at_all():
    page = FakePage({VIDEOJS})
    assert Camera(page, "#video-player46").video_selector() == VIDEOJS


def test_neither_player_visible_fails_saying_what_was_found_and_its_state():
    page = FakePage({WHEP, VIDEOJS}, hidden={WHEP, VIDEOJS})
    with pytest.raises(CameraNotShown) as caught:
        Camera(page, "#video-player46").video_selector()
    message = str(caught.value)
    assert f"the WHEP <video> ({WHEP}): in the page but not visible" in message
    assert f"the video.js <video> ({VIDEOJS}): in the page but not visible" in message


def test_a_missing_player_is_reported_as_not_in_the_page():
    with pytest.raises(CameraNotShown, match=r"not in the page"):
        Camera(FakePage(set()), "#video-player46").video_selector()


def test_player_state_reports_nothing_displayed_instead_of_raising():
    state = Camera(FakePage({WHEP}, hidden={WHEP}), "#video-player46").player_state()
    assert "no camera picture is displayed" in state["error"]


class _ShotPage(FakePage):
    """Takes a screenshot only of an element that is visible, as Playwright does."""

    def locator(self, selector):
        locator = super().locator(selector)

        def screenshot():
            if selector in self.hidden:
                raise TimeoutError("element is not visible")
            return _PNG

        locator.screenshot = screenshot
        return locator


def _png():
    buffer = io.BytesIO()
    Image.new("RGB", (4, 4)).save(buffer, "PNG")
    return buffer.getvalue()


_PNG = _png()


def test_a_shot_is_taken_of_the_displayed_element_and_the_hidden_one_is_never_asked():
    page = _ShotPage({WHEP, VIDEOJS}, hidden={VIDEOJS})
    assert Camera(page, "#video-player46").shot().size == (4, 4)


def test_a_shot_with_nothing_displayed_raises_with_the_element_states():
    page = _ShotPage({WHEP, VIDEOJS}, hidden={WHEP, VIDEOJS})
    with pytest.raises(CameraNotShown, match="not visible"):
        Camera(page, "#video-player46").shot()


def test_the_wait_for_a_live_picture_reports_which_elements_were_found():
    """check_live (and so check_live_with_recovery) says why, in words, when nothing is displayed."""
    page = _ShotPage({WHEP, VIDEOJS}, hidden={WHEP, VIDEOJS})
    live, detail = Camera(page, "#video-player46").check_live(timeout=0.01, gap=0.0)
    assert not live
    assert "could not read the picture" in detail and "the WHEP <video>" in detail
