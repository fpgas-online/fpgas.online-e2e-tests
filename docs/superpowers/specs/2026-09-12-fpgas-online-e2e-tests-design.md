# Design: fpgas.online end-to-end browser tests

**Date**: 2026-09-12
**Status**: Draft, awaiting Tim's review
**Author**: Tim Ansell + Claude

## Summary

A new public repository, `fpgas-online/fpgas.online-e2e-tests`, holding a
browser-driven test suite that uses the live fpgas.online sites the way a
human does: it opens the board pages in a real browser, clicks the buttons,
types into the web terminal the site provides, watches the camera, and
uploads bitstreams through the site's own form.

The suite runs on a schedule in GitHub Actions every six hours against
production. It needs no secrets: every credential it uses is one the site
hands to any visitor.

Two test sets:

- **shared** -- runs against `welland.fpgas.online` and `ps1.fpgas.online`,
  which serve the same `/fpgas/` application.
- **tinytapeout** -- runs against `tinytapeout.fpgas.online`, which is a
  different application with a different UI.

The first three tests are power cycling, bitstream upload on an Arty, and
direct ssh following the instructions printed on the board page. After those,
the suite grows a test per control in the UI, Arty first, then the Acorn
boards, then the Tiny Tapeout functionality.

## Goals

1. Detect, within six hours, any regression that stops a real user doing a
   real thing on a real board.
2. Validate the *depth* of one path rather than the *breadth* of identical
   paths. If PoE control works on one board, the suite does not prove it on
   thirteen more.
3. Never pass on the site's own word alone. Every test must produce at least
   one piece of evidence from outside the web application.
4. Behave like a visitor: no API shortcuts, no test hooks, no credentials
   that a visitor could not obtain.
5. Stay unobtrusive enough that a user colliding with a test run is rare, and
   harmless when it happens.

## Non-goals

- Cross-browser testing. Nobody is asking whether the site works in Safari.
- Load or performance testing.
- Testing the marketing site at `fpgas.online` (GitHub Pages, static).
- Unit testing the Django applications. That belongs in
  `fpgas.online-site`.

## Background: what the UI actually is

Findings from reading the deployed code and probing the live sites on
2026-09-12. They drive most of the decisions below.

**The two shared sites run different code.** `welland.fpgas.online` serves
current `fpgas.online-site` main: board cards are headed `pi-sw2-p16` and the
"Edit this page" links point at `fpgas-online/fpgas.online-site`.
`ps1.fpgas.online` still serves the pre-split monorepo build: cards headed
`FPGA pi2`, links pointing at `CarlFK/pici`. Welland has 14 boards (4 Arty
A7-35T, 6 Sqrl Acorn CLE-215+, 4 TT FPGA emulation); PS1 has 9.

**The board page is a thin shell over four independent backends.**

| Control | Backend |
|---|---|
| `Reset`, `Check PoE` | `POST /snmp/toggle`, `/snmp/status` -- SNMP to the PoE switch |
| Upload form | `POST /pibup/upload` -- Django sftps the file to the Pi with paramiko |
| Demo buttons | Type a command into the web terminal (`wssh.send`) |
| Status log box | Django Channels WebSocket `/ws/pistat/pi<N>/` |

**The web terminal is [WebSSH](https://github.com/huashengdun/webssh)** at
`/wssh/`, embedded in an iframe whose URL carries the connection details:
`?hostname=10.21.2.16&username=pi&title=pi-sw2-p16&password=<PI_PW>` (base64,
which WebSSH's client decodes with `atob`). It needs no credentials from us:
the page supplies them.

**The terminal is a shared `tmux` session.** Logging in runs a wrapper that
attaches to a session named `default`, so everyone who opens a given board
page is looking at and typing into the *same* shell. Consequences for the
suite: commands it types are visible to anyone else on that board, its reads
can pick up other people's output, and the screen is redrawn constantly, so
the output buffer essentially never *ends* at a prompt. Prompt detection
therefore searches per line rather than anchoring to the end of the buffer.

That is necessary but not sufficient. A shell already sitting at a prompt has
nothing left to say, so after a buffer reset -- or after navigating back to
the page -- the prompt was printed before this reading started and the only
new bytes are tmux repainting its status bar. Waiting on the stream alone
waits forever for something that already happened, while the screen plainly
shows a prompt. `wait_for_prompt` therefore presses Enter if the terminal
stays quiet, which is what a person does when unsure a terminal is alive; it
costs one blank line in the shared session. The 6 s grace before the first
press keeps it out of the way of a normal login, which reaches its first
prompt in about 5 s.

**WebSSH's two WebSocket directions are not symmetric.** Client to server is
JSON (`sock.send(JSON.stringify({'data': data}))`). Server to client is
*binary frames of raw terminal bytes*, which its client hands straight to
xterm via `read_file_as_text(msg.data, term_write, decoder)`. There is no JSON
to unwrap on the way in.

**The terminal renders to a canvas, so its text is not in the DOM.** WebSSH
bundles xterm.js 4.x -- its `main.js` reads
`term._core._renderService._renderer.dimensions`, a v4-only shape, and the
bundle still carries the `rendererType` option that v5 removed. WebSSH never
sets `rendererType`, so the v4 default (canvas) applies and `.xterm-rows`
stays empty. WebSSH also keeps its `Terminal` instance in a closure, so the
xterm buffer API is unreachable from outside.

**The camera stream is H.264/AAC in MPEG-TS.** Parsing the PMT of a live
segment from `/live/pi-sw2-p16.m3u8` gives `stream_type=0x1b (H.264/AVC)` and
`stream_type=0x0f (AAC)`. `fpgas.online-cam/tests/ci/Dockerfile` says
Playwright's bundled Chromium cannot decode this -- it "reports
MEDIA_ERR_SRC_NOT_SUPPORTED on this stream" -- and drives Debian's
`chromium` instead.

**That is no longer true, and the real obstacle is different.** Tested
against the live stream on 2026-09-12, Playwright's bundled chromium
(151.0.7922.34) decodes it to 1280x1080 at `readyState` 4, exactly as Google
Chrome does. What *does* stop the video is the browser's **autoplay policy**:
without `--autoplay-policy=no-user-gesture-required` the player never starts,
leaving `readyState` 0, `paused` true and `error` null -- which looks exactly
like a missing codec and is not. The suite passes that flag and uses the
bundled browser; no distribution browser is required.

`MediaSource.isTypeSupported('video/mp4; codecs="avc1.42E01E"')` was tried as
a guard against a codec-less browser and rejected: it answers true on both
builds, so it discriminates nothing. The honest check is whether the picture
is actually advancing, which the liveness primitive already does.

**The Pi burns a clock overlay into the camera picture.**
`fpgas.online-cam/tests/measure-latency.mjs` OCRs it with tesseract to
measure glass-to-glass latency. Because the camera runs *on the Pi*
(`fpgas-online-cam`'s `cam.service`), that clock stops when the board loses
power and resumes when it returns -- visible ground truth for a power cycle,
requiring no cooperation from the web application.

**The "password is in login banner" promise is real, but not where a naive
read looks.** Reading the raw socket gets only the `SSH-2.0-OpenSSH_...`
version string. The banner the page means is `SSH_MSG_USERAUTH_BANNER`, sent
*during* authentication, which is why a real ssh client prints it just before
the password prompt. Fetched properly from `ps1.fpgas.online:10222` it is the
password on a line by itself, matching the base64 in that site's iframe URL.
So the suite reads it the way a client does: start a transport, attempt the
`none` auth method every server rejects, and take the banner that elicits.

**The per-board ssh ports advertised on welland are unreachable.** The board
page tells users `ssh -p 21622 pi@welland.fpgas.online`. That port times out
from the public internet over both IPv4 and IPv6, as does 24222, while
`welland.fpgas.online:22` answers and `ps1.fpgas.online:10222` answers with a
real Pi banner. Test 3 is therefore expected to fail on welland from the
first run.

```
welland.fpgas.online:22     OPEN b'SSH-2.0-OpenSSH_10.0p2 Debian-7+deb13u4'  (IPv6)
welland.fpgas.online:22     OPEN b'SSH-2.0-OpenSSH_10.4p1 Debian-4'          (IPv4)
welland.fpgas.online:21622  TimeoutError   (both families)
welland.fpgas.online:24222  TimeoutError
ps1.fpgas.online:10222      OPEN b'SSH-2.0-OpenSSH_10.0p2 Raspbian-7+deb13u1'
```

**welland's web terminal never authenticates.** Loaded in a real browser, the
wssh iframe logs `Authentication failed.` then `socket closed.`, and no
`/wssh/ws` WebSocket is opened at all. PS1's terminal connects normally from
the same browser, so this is welland-specific. Since the web terminal is the
suite's primary channel for shell work, this blocks tests 1 and 2 there.

**welland's `POST /snmp/status` returns HTTP 500.** The board page calls it on
load, so the status box never learns the PoE state. PS1 answers `{state: on}`.

Worth stating plainly: **PS1 runs older code but is in better health.** Its
web terminal connects, its PoE status endpoint answers, and its ssh forward
ports are reachable -- all three broken on welland.

Two things checked and found *not* to be broken, recorded so nobody
re-investigates: the VLC URL the page prints (`/live/pi16.m3u8`) and the
stream the player uses (`/live/pi-sw2-p16.m3u8`) both return live, advancing
playlists; they are aliases. `/fpgas/tt.html` returns 404 on both sites,
because the view hardcodes port 21, but nothing links to it.

## The evidence model

The central rule, and the thing that distinguishes this suite from a
click-through script:

> **A claim** is something the web application says about itself: a line in
> the status log box, a success page, a green pill. A claim may be asserted
> on, because "does the status box work" is itself a feature under test. A
> claim may never be the only thing a test passes on, because a claim can
> lie.
>
> **Ground truth** is something observed outside the web application: the
> camera picture, the Pi's own uptime, a file that really exists on the Pi,
> an ssh server that really answers.

This is mechanical, not cultural. `e2e/evidence.py` provides
`claim(...)` and `ground_truth(...)` assertion wrappers, and a session
fixture fails any test that finishes without recording at least one
ground-truth assertion -- so a test cannot silently decay into a
claim-only test as the UI changes.

A small number of controls can only ever be claim-verified; the "Send"
WebSocket echo button is one, since it echoes the tester's own text back.
Those are marked `@claim_only` with a written reason, which both exempts them
from the fixture and documents *why* no stronger evidence exists.

### Reading the terminal

Terminal text has three independent sources, and the suite requires them to
agree:

1. **The WebSSH WebSocket frames** (`{"data": "..."}`), read through
   Playwright's `framereceived`. Cheap, exact, and the same bytes that get
   painted -- but it is transport, not screen, so on its own it is a claim
   about what is displayed.
2. **Clipboard copy.** Drag-select the terminal viewport and copy, which is
   the gesture a human uses to grab terminal output.
3. **OCR** of a screenshot of the terminal, with tesseract.

`WebTerminal.run(cmd)` returns all three. Disagreement beyond normalisation
of whitespace and line wrapping is a failure with all three attached, because
it means the user is not seeing what the server sent.

OCR runs against the terminal **as the site renders it by default**. The
suite does not pass WebSSH's `fontsize`, `fontcolor` or `bgcolor` URL options
to make the text easier to read: if OCR cannot read the terminal at default
settings, humans are probably struggling too, and that is a finding rather
than something to work around.

### Reading the camera

Assertions use **screenshots of the video element as rendered**, not frames
pulled out of the decoder. Reading frames directly (drawing to a canvas via
`page.evaluate`, as `measure-latency.mjs` does) is reserved for the rare case
where a screenshot genuinely cannot answer the question, and each such use
must say why in a comment.

Two primitives cover most needs:

- **Is the feed live?** OCR the burned-in clock across two screenshots taken
  a few seconds apart and check it advanced. This distinguishes a live feed
  from a frozen one, which a naive "is the picture non-black" check cannot.
- **Did the picture change?** Compare screenshots and report a normalised
  difference, optionally restricted to a region such as the LED bank.

## Architecture

```
fpgas.online-e2e-tests/
├── e2e/                        the library the tests are written against
│   ├── evidence.py             claim() / ground_truth(); the enforcing fixture
│   ├── site.py                 Site: base URL, boards discovered from /fpgas/
│   ├── board.py                Board: hostname, port, fpga_board, page URL
│   ├── terminal.py             WebTerminal: keystroke input, triangulated read
│   ├── statuslog.py            StatusLog: the rendered textarea; claims only
│   ├── camera.py               Camera: screenshots, clock OCR, diffing
│   ├── ocr.py                  tesseract wrapper
│   └── picker.py               random board choice; --on-dead=fail|retry
├── tests/
│   ├── conftest.py             --site, --on-dead, --seed; browser fixtures
│   ├── shared/                 welland + ps1
│   │   ├── test_power_cycle.py
│   │   ├── test_bitstream_upload.py
│   │   └── test_direct_ssh.py
│   └── tinytapeout/
├── fixtures/counter_test/top.bit
├── docs/ROADMAP.md             the audit and phase plan from this spec
└── .github/workflows/e2e.yml
```

The **library is the deliverable**, not the first three tests. The roadmap
adds roughly thirty-five more tests; if `WebTerminal`, `Camera` and
`StatusLog` are solid, each is a dozen lines, and if they are inlined into
the first three tests, test twelve is a rewrite.

**Boards are discovered, never hardcoded.** `Site.boards()` parses `/fpgas/`
for the board cards -- the page a user lands on -- and yields
`Board(hostname, port, fpga_board)`. New hardware needs no code change, and
PS1's different card format is one parser branch.

**Every board is assumed to be an Arty.** The original design derived a
`kind` from the board name (`Digilent Arty A7-35T` -> `arty`, `Sqrl Acorn
CLE-215+` -> `acorn`) and selected on it. In practice that meant the Arty
tests ran nowhere: PS1 names no FPGA at all, so every board there parsed as
`unknown` and the tests failed on the selection gate, in 21 seconds, without
opening a board page; welland names types but its terminal is down
fleet-wide. Selecting on the advertised type made the suite hostage to the
index page's copy. A board that turns out not to be an Arty now fails inside
the test, where the message names the real problem, and the thin PS1 card is
reported as the user-facing fault it is.

### Handling the version skew

The suite **fails loudly on any difference**. A control the suite expects and
cannot find is a failure, not a skip, on every site. PS1 will therefore be red
until it is upgraded to current `fpgas.online-site`. That is deliberate: a
suite that quietly tolerates PS1 being a year behind would stop being
evidence that PS1 works.

### Stack

**pytest + Playwright for Python**, driving Playwright's own chromium, with
paramiko for the one direct-ssh test, tesseract for OCR, and Pillow + NumPy
for image comparison.

Playwright rather than Selenium is not a style preference; two capabilities
decide it:

- **WebSocket frames.** Playwright's `WebSocket` class fires `framereceived`
  and `framesent` (since v1.9). Selenium's replacement protocol, WebDriver
  BiDi, defines exactly five network events -- `network.authRequired`,
  `network.beforeRequestSent`, `network.fetchError`,
  `network.responseCompleted`, `network.responseStarted` -- and none for
  WebSocket frames. Since the terminal is a canvas, the WebSocket is the only
  cheap path to its text, so on Selenium the suite's primary channel would
  have no supported reader at all.
- **Artefacts.** `pytest-playwright` provides `--screenshot
  only-on-failure`, `--video retain-on-failure` and `--tracing
  retain-on-failure` into `--output test-results`. On Selenium all of that is
  hand-rolled.

Python rather than TypeScript because half this suite is not browser work --
ssh, OCR, image differencing -- and because every other repo in the
organisation is Python with `uv`. Playwright itself is already in house:
`fpgas.online-cam/tests` drives `playwright-core` against the system
chromium.

Auto-waiting matters more than usual here. The suite waits on physical events
-- a Pi booting, an FPGA being programmed -- and Playwright's web-first
assertions retry until timeout by construction, where Selenium needs explicit
waits at every step.

## The first three tests

Steps are tagged **[G]** ground truth or **[C]** claim.

### Test 1 -- power cycling

On a random board page:

1. Confirm the feed is live: OCR the burned-in clock in two screenshots a few
   seconds apart and see it advance. **[G]**
2. In the web terminal, read `/proc/uptime` -> `U0`. **[G]**
3. Click **Reset**.
4. The status log box shows the SNMP power off and on lines. **[C]**
5. Within ~15 s the feed stops being live -- either the clock stops
   advancing or the player errors out, both of which mean the Pi stopped
   sending, because the camera runs on the Pi that just lost power. **[G]**
6. Within ~180 s the feed returns and the clock resumes. **[G]**
7. The terminal session died with the Pi, so click **reset ssh** as a human
   would, then read `/proc/uptime` again: `U1 < U0`, and `U1` under ~180 s.
   **[G]**
8. The status log box shows the Pi's boot reports. **[C]**

### Test 2 -- bitstream upload on an Arty

1. Screenshot the video region as baseline `B0`.
2. Submit `fixtures/counter_test/top.bit` through the page's upload form.
3. The success page renders. **[C]**
4. In the web terminal, `ls -l Uploads/top.bit` shows the right size. **[G]**
5. `openFPGALoader -b arty Uploads/top.bit` in the terminal, and read its
   output. **[G]**
6. Screenshots afterwards differ from `B0` in the LED region, and successive
   screenshots differ from each other -- the counter is visibly counting.
   **[G]**

*Known limitation.* `counter_test/top.bit` is the same bitstream the "Blink
LEDs" button loads, so the camera can prove "the LEDs changed and are now
counting" but not "this upload is what is running". A distinctive design from
`fpgas.online-test-designs` closes that gap later; using the existing file
first keeps the suite free of new artefacts.

### Test 3 -- direct ssh per the instructions on the page

1. Parse the rendered instructions from the board page -- user, host, port,
   and both click-to-copy blocks -- because that is what a human copies.
2. Connect to that host and port and read the ssh banner; extract the
   password from it. **[G]**
3. Authenticate as `pi` with that password. **[G]**
4. Run `hostname`; it matches the name shown on the page. **[G]**
5. Cross-check `hostname` through the web terminal, so a pass proves both
   routes reach the same board.
6. Verify the site's *other* documented credential path also works: the
   password the board page embeds in the wssh iframe URL authenticates
   directly too.

Expected to fail on welland until the per-board ssh forwards are reachable.

## Board selection and not being disruptive

**Selection.** Boards come from `/fpgas/` and are shuffled with a run-seeded
RNG whose seed is printed, so any run can be replayed against the same board.
There is no filtering: every board the index lists is a candidate. Before committing to a board, a
~20 s liveness glance: the page loads, the video is playing, the terminal
reaches a prompt.

**Dead boards.** Two modes, selected by `--on-dead`:

- `fail` (default, and what the schedule uses) -- a dead board is a real
  user-facing fault. Report it, name the board, stop.
- `retry` -- pick another board and carry on, still reporting the dead one.
  For manual runs where the deep tests are the point.

**Not being disruptive.**

- The suite **never** calls `/snmp/toggle_all` or `/snmp/off_all`. They exist
  and would take out the whole site; no user journey reaches them, so neither
  does the suite.
- A GitHub Actions `concurrency` group per site prevents a manual run
  colliding with the schedule. Cheaper and cleaner than lock files on the
  Pis.
- With 14 boards on welland, 9 on PS1 and 6-hourly runs, a given board is
  touched every few days.
- Tests do not restore prior state -- visible side effects are accepted --
  but must not leave a board worse than found. After test 2 the Arty runs
  `counter_test`, a normal state a user could have left it in.

## Continuous integration

`.github/workflows/e2e.yml`:

- `schedule: "0 */6 * * *"`, plus `workflow_dispatch` with `site`, `seed`
  (to replay a previous run's board choice) and `on_dead`.
- A matrix over `welland` and `ps1` for the shared tests with
  `fail-fast: false`, so PS1's expected redness never masks a welland
  regression. A separate job for `tinytapeout`.
- `concurrency: e2e-${{ matrix.site }}`, `cancel-in-progress: false`.
- Runner setup: `apt install tesseract-ocr tesseract-ocr-eng
  fonts-dejavu-core` for OCR, then `playwright install --with-deps chromium
  ffmpeg` -- `ffmpeg` is what `--video` recording needs, and without it every
  test errors during setup.
- Artefacts uploaded on **every** run, not only failures, at least initially:
  a green run's screenshots are what shows the OCR and camera thresholds are
  calibrated rather than accidentally passing.
- No secrets. Every credential comes from the site itself, so the repository
  is public, forkable and runnable by anyone against either site -- itself a
  fair test of the claim that this is a public service.

On failure: the red run and GitHub's own notification, plus the artefacts.
No issue-filing automation.

### Running it locally

The same entry point the workflow uses, so a failing scheduled run can be
reproduced by hand from the seed it printed:

```bash
uv run pytest tests/shared --site welland
uv run pytest tests/shared --site welland --seed 1789203319 --on-dead retry
uv run pytest tests/tinytapeout
uv run pytest tests/shared --site ps1 -k power_cycle --headed
```

`--site` takes `welland` or `ps1` and resolves to `https://<site>.fpgas.online`.
Local runs need the same `tesseract-ocr` package and browser install as CI;
`--headed` watches the run in a real window, which is how the camera and OCR
thresholds get calibrated in the first place.

## Roadmap

### Phase 1 -- Arty, board page (`/fpgas/pi<N>.html`)

Highest priority. A test per control, with what makes each ground truth:

| Control | What a passing test proves |
|---|---|
| `Reset` | Test 1 |
| `reconnect` | Status box says reconnected **[C]**; then `Check PoE` still gets a reply, proving the socket works rather than merely said so |
| `reset video player` | Stall the player, click, screenshots show the clock advancing again |
| `reset ssh` | Fresh banner and prompt; `tty` reports a different pts than before |
| `ping` | Status box shows replies **[C]**; the IP pinged matches the board's, and 3/3 replies arrive |
| `Blink LEDs` | Terminal shows the demo running; camera shows the LEDs counting |
| `Load MicroPython` | Terminal reaches a MicroPython REPL; `print(6*7)` returns `42` |
| `Boot Linux` | Terminal shows the LiteX boot log reaching a login prompt on the soft CPU |
| `Check Wire` | Terminal reports exit status 0; status box shows the PMOD result **[C]** |
| `Check PoE` | Status box reports power on **[C]**, cross-checked against a live feed |
| `Send` (WS test) | Claim-only by nature: it echoes the tester's own text. Marked `@claim_only` |
| Click-to-copy blocks | Clipboard matches the rendered text, and the copied `ssh` command connects (test 3) |
| VLC URL | The `.m3u8` the page prints returns an advancing playlist |
| Upload form | Test 2 |
| Video.js controls | Pause freezes the picture, play resumes it, mute and fullscreen respond -- all by screenshot |

### Phase 1b -- index page (`/fpgas/`)

One card per board with the right name and FPGA type; every card's video is
live, which doubles as a whole-fleet health sweep and is the cheapest
high-value test in the suite; "Use this FPGA" lands on the board whose name
matches the card; the header links resolve.

### Phase 2 -- Acorn CLE-215+

Six boards on welland, all on Pi 5s, so the programming path is the
`rp1-jtag` bit-banged JTAG rather than the Arty's USB `openFPGALoader` -- a
genuinely different code path, which is why it is its own phase.
`fpgas.online-test-designs` already carries Acorn-targeted designs
(`spi-flash-id`, `pcie-enumeration`, `ddr-memory`, `ethernet-test`,
`pmod-pin-id`), so the deep test is: upload an Acorn bitstream through the
web form, program it over JTAG from the web terminal, and read the design's
result back.

The audit should also record what the Arty-specific demo buttons do on an
Acorn board page, since today they are offered to users regardless of the
fitted hardware.

### Phase 3 -- Tiny Tapeout

Its own suite against `tinytapeout.fpgas.online`: catalogue cards and
live/coming-soon states; the status pill; `Power-cycle board`; `Reset video`;
the Commander embed's serial terminal over the RP2040 WebSocket bridge; the
design gallery loading from the Pi daemon; Run/enable with a `clock_hz`; the
`.bin` upload form including its 256 KiB cap and 16-file eviction; and the
legacy `/fpgas/tt.html` route, which currently 404s on both sites.

## Repository setup

`fpgas-online/fpgas.online-e2e-tests`, public, Apache 2.0, configured per
`~/.claude/GitHub.md`: wiki, projects and discussions disabled; merge commits
only; delete branch on merge; secret scanning and push protection on; default
branch protected against force pushes and deletion; `v0.0` tagged on the
first commit; tag ruleset applied (format to be confirmed -- `vXX.ZZZ` is the
default).

## Open questions

1. **Tag version format** for the ruleset: `vXX.ZZZ` (default) or
   `vXX.YY.ZZZ`.
2. **Whether test 3 failing on welland should block the initial merge**, or
   land red as the suite's first real finding.
