# fpgas.online-e2e-tests

End-to-end browser tests for the [fpgas.online](https://fpgas.online) sites.

The suite uses the live sites the way a person does: it opens the board pages
in a real browser, clicks the buttons, types into the web terminal the site
provides, watches the camera, and uploads bitstreams through the site's own
form. It needs no secrets -- every credential it uses is one the site hands
to any visitor.

## Running

Requires an OCR engine, Google Chrome, the ssh client, and a display:

    sudo apt install tesseract-ocr tesseract-ocr-eng fonts-dejavu-core xvfb openssh-client
    uv run playwright install chrome ffmpeg

`ffmpeg` is what `--video` recording uses; without it every test errors during
setup.

**The suite runs Google Chrome with a window, because that is what a user
runs.** It refuses anything else: at session start it asks the browser what it
tells the site about itself and stops unless the brands include "Google
Chrome" and the user agent is not the headless variant. Playwright's bundled
Chromium announces itself as `HeadlessChrome/151`, which no person browses
with. Without a display, give it one:

    xvfb-run -a uv run pytest tests/shared --site ps1

The camera feed is H.264 in MPEG-TS and plays under Chrome's default autoplay
policy: the page's `<video>` is muted. No launch flags are needed or used.

Then:

    uv run pytest tests/unit                                    # offline, no site contact
    xvfb-run -a uv run pytest tests/shared --site welland      # against production
    xvfb-run -a uv run pytest tests/shared --site ps1
    xvfb-run -a uv run pytest tests/shared --site welland --seed 1234 --on-dead retry
    uv run pytest tests/shared --site welland -k power_cycle   # on a desktop: watch it

`--site` takes `welland` or `ps1`. Each run prints the random seed it used, so
a failure can be replayed against the same board with `--seed`.

## Auditing a whole site

    xvfb-run -a uv run pytest tests/audit --site ps1 -s

Where a test picks one board and stops at the first thing wrong, the audit
visits every board the index lists and runs the same journeys on each,
producing one row per board:

    ### ps1: 9 boards, audited 2026-09-14T04:10:22Z
    board  page  camera             terminal  poe status  ssh   upload  power cycle
    pi2    ok    FAIL               FAIL      ok (on)     FAIL  FAIL    FAIL
    pi7    ok    ok (reset needed)  ok        ok (on)     ok    FAIL    ok
    ...

    why:
      pi2 camera: ...

The table is printed at the end, written to `<output>/audit-<site>.md`, and
on GitHub appended to the job summary. A cell passes only if every
observation in that journey held; the reasons under the table quote what was
seen. The test fails if any cell failed.

It power-cycles every board, so it is not on the six-hourly schedule: run it
from the Actions page with the "audit" box ticked, or by hand. `--boards
pi7,pi9` narrows it during development.

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
