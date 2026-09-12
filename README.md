# fpgas.online-e2e-tests

End-to-end browser tests for the [fpgas.online](https://fpgas.online) sites.

The suite uses the live sites the way a person does: it opens the board pages
in a real browser, clicks the buttons, types into the web terminal the site
provides, watches the camera, and uploads bitstreams through the site's own
form. It needs no secrets -- every credential it uses is one the site hands
to any visitor.

## Running

Requires an OCR engine and a browser:

    sudo apt install tesseract-ocr tesseract-ocr-eng fonts-dejavu-core
    uv run playwright install chromium ffmpeg

`ffmpeg` is what `--video` recording uses; without it every test errors during
setup.

The camera feed is H.264 in MPEG-TS. Playwright's bundled chromium decodes it
fine (measured 2026-09-12 on 151.0.7922.34: 1280x1080, `readyState` 4), so no
distribution browser is needed -- but the suite must launch with
`--autoplay-policy=no-user-gesture-required`, which `tests/conftest.py` does.
Without it the player silently never starts: `readyState` stays 0 with no
error, which looks exactly like a codec failure and is not. Set `$CHROMIUM` to
use a different browser binary.

Then:

    uv run pytest tests/unit                       # offline, no site contact
    uv run pytest tests/shared --site welland      # against production
    uv run pytest tests/shared --site ps1
    uv run pytest tests/shared --site welland --seed 1234 --on-dead retry
    uv run pytest tests/shared --site welland -k power_cycle --headed

`--site` takes `welland` or `ps1`. Each run prints the random seed it used, so
a failure can be replayed against the same board with `--seed`.

## How it decides something works

A **claim** is what the site says about itself: a line in the status log box, a
success page. A test may assert on a claim, because "does the status box work"
is itself a feature under test -- but it may never *pass* on claims alone,
because a claim can lie.

**Ground truth** is what is observable outside the web application: the camera
picture, the Pi's own uptime, a file that really exists on the Pi, an ssh
server that really answers.

This is enforced, not merely encouraged: a test that finishes without recording
any ground truth fails, unless it is marked `@pytest.mark.claim_only` with a
reason no stronger evidence is possible.

## What it tests

See [docs/ROADMAP.md](docs/ROADMAP.md).

These tests run against the **live production** service. They have real,
user-visible side effects: a board gets power-cycled, an FPGA gets
reprogrammed. One board is picked at random per run, so any given board is
touched rarely.

## Licence

Apache 2.0
