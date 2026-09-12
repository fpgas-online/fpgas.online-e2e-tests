"""Camera must find the real <video>, not video.js's wrapper.

video.js moves the id from the <video> onto a wrapper <div> and renames the
element to "<id>_html5_api". Verified on ps1.fpgas.online 2026-09-12:

    #video-player2        -> DIV.video-js ...      (currentTime undefined)
    #video-player2 video  -> VIDEO#video-player2_html5_api  (currentTime number)

So the selector the page author wrote resolves to something with no media
properties at all once the player has initialised.
"""

from e2e.camera import Camera


class FakeLocator:
    def __init__(self, count):
        self._count = count

    def count(self):
        return self._count


class FakePage:
    """Records what was asked for; reports which selectors exist."""

    def __init__(self, existing):
        self.existing = existing
        self.evaluated = []

    def locator(self, selector):
        return FakeLocator(1 if selector in self.existing else 0)

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
