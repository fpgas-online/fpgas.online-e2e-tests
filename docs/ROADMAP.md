# Test roadmap

**Implemented:** a board page's camera and terminal (the fleet-health test),
power cycling, bitstream upload on an Arty, and direct ssh following the
instructions on the board page.

The harness is verified end to end against production. From a run on
2026-09-12 against `ps1.fpgas.online`:

```
[e2e] testing on pi2
  ok  [ground truth] the index page lists at least one board
  ok  [ground truth] pi2's camera is showing a live picture
        clock '15:11:01' -> '15:11:04'; readyState 4, videoWidth 1280
  ok  [ground truth] the web terminal reaches the board the page says it is
  ok  [ground truth] the Pi answers a second command
```

That one test exercises everything: the camera assertion OCRs the clock the
Pi burns into the picture and sees it advance, and each terminal command is
read three ways -- WebSocket bytes, clipboard copy, and OCR of the canvas
pixels -- and required to agree.

The scheduled suite validates the *depth* of one path, not the breadth of
identical paths: one board is picked at random per run. The breadth is the
**audit** (`tests/audit`), which runs every journey on every board the index
lists and prints one row per board -- page, camera, terminal, PoE status,
ssh, upload, power cycle -- so that "what is the state of the site" is a
table the suite produces rather than something measured by hand. It is run on
demand, because it power-cycles every board.

Every board is assumed to be an Arty. The sites do not reliably say what FPGA
is fitted -- ps1 names none at all -- so selecting by the advertised type only
meant the Arty tests refused to run anywhere. A board that turns out not to be
an Arty now fails inside the test, where the failure names the real problem
rather than being hidden behind a selection gate.

Steps are tagged **[G]** ground truth (observed outside the web application)
or **[C]** claim (what the site says about itself). A test may assert on a
claim, but may never pass on claims alone.

## Phase 1 -- Arty, board page (`/fpgas/pi<N>.html`)

Highest priority: a test per control.

| Control | What a passing test proves |
|---|---|
| `Reset` | Implemented -- `test_power_cycle.py` |
| `reconnect` | Status box says reconnected **[C]**; then `Check PoE` still gets a reply, proving the socket works rather than merely said so |
| `reset video player` | Stall the player, click, screenshots show the burned-in clock advancing again |
| `reset ssh` | Fresh login banner and prompt; `tty` reports a different pts than before |
| `ping` | Status box shows replies **[C]**; the IP pinged matches the board's, and 3/3 replies arrive |
| `Blink LEDs` | Terminal shows the demo running; camera shows the LEDs counting |
| `Load MicroPython` | Terminal reaches a MicroPython REPL; `print(6*7)` returns `42` |
| `Boot Linux` | Terminal shows the LiteX boot log reaching a login prompt on the soft CPU |
| `Check Wire` | Terminal reports exit status 0; status box shows the PMOD result **[C]** |
| `Check PoE` | Status box reports power on **[C]**, cross-checked against a live camera feed |
| `Send` (WS test) | *Claim-only by nature*: it echoes the tester's own text back. To be marked `@pytest.mark.claim_only` |
| Click-to-copy blocks | Clipboard matches the rendered text, and the copied `ssh` command connects |
| VLC URL | The `.m3u8` the page prints returns an advancing playlist |
| Upload form | Implemented -- `test_bitstream_upload.py` |
| Video.js controls | Pause freezes the picture, play resumes it, mute and fullscreen respond -- all by screenshot |

## Phase 1b -- index page (`/fpgas/`)

One card per board with the right name and FPGA type; every card's video is
live, which doubles as a whole-fleet health sweep and is the cheapest
high-value test in the suite; "Use this FPGA" lands on the board whose name
matches the card; the header links resolve.

## Phase 2 -- Acorn CLE-215+

Six boards on welland, all on Pi 5s, so the programming path is the
`rp1-jtag` bit-banged JTAG rather than the Arty's USB `openFPGALoader` -- a
genuinely different code path, which is why it is its own phase.
[fpgas.online-test-designs](https://github.com/fpgas-online/fpgas.online-test-designs)
already carries Acorn-targeted designs (`spi-flash-id`, `pcie-enumeration`,
`ddr-memory`, `ethernet-test`, `pmod-pin-id`), so the deep test is: upload an
Acorn bitstream through the web form, program it over JTAG from the web
terminal, and read the design's result back.

The audit should also record what the Arty-specific demo buttons do on an
Acorn board page, since today they are offered to users regardless of the
fitted hardware.

## Phase 3 -- Tiny Tapeout

Its own suite against `tinytapeout.fpgas.online`, which is a different
application with a different UI: catalogue cards and live/coming-soon states;
the status pill; `Power-cycle board`; `Reset video`; the Commander embed's
serial terminal over the RP2040 WebSocket bridge; the design gallery loading
from the Pi daemon; Run/enable with a `clock_hz`; the `.bin` upload form
including its 256 KiB cap and 16-file eviction. The legacy `/fpgas/tt.html`
route is in scope only if that site links to it; on welland and ps1 nothing
does, and an address no user can reach is not worth a test.

## Known production faults this suite reports

The state of both sites, as measured by the audit on 2026-09-14 with the
same instrument on the same day. The full reports, with what was seen for
every cell, are in [docs/audits/](audits/).

### welland, 14 boards ([report](audits/2026-09-14-welland.md))

| board | page | camera | terminal | poe status | ssh | upload | power cycle |
|---|---|---|---|---|---|---|---|
| pi-sw2-p16 | ok | ok | FAIL | FAIL (not shown) | FAIL | FAIL | FAIL |
| pi-sw2-p29 | ok | ok | FAIL | FAIL (not shown) | FAIL | FAIL | FAIL |
| pi-sw2-p33 | ok | FAIL | FAIL | FAIL (not shown) | FAIL | FAIL | FAIL |
| pi-sw2-p34 | ok | ok | FAIL | FAIL (not shown) | FAIL | FAIL | FAIL |
| pi-sw2-p35 | ok | ok | FAIL | FAIL (not shown) | FAIL | FAIL | FAIL |
| pi-sw2-p36 | ok | ok (reset needed) | FAIL | FAIL (not shown) | FAIL | FAIL | FAIL |
| pi-sw2-p37 | ok | FAIL | FAIL | FAIL (not shown) | FAIL | FAIL | FAIL |
| pi-sw2-p38 | ok | ok | FAIL | FAIL (not shown) | FAIL | FAIL | FAIL |
| pi-sw2-p42 | ok | ok | ok | FAIL (not shown) | FAIL | FAIL | FAIL |
| pi-sw2-p43 | ok | FAIL | FAIL | FAIL (not shown) | FAIL | FAIL | FAIL |
| pi-sw2-p44 | ok | ok | FAIL | FAIL (not shown) | FAIL | FAIL | FAIL |
| pi-sw2-p46 | ok | ok | FAIL | FAIL (not shown) | FAIL | FAIL | FAIL |
| pi-sw2-p47 | ok | ok | FAIL | FAIL (not shown) | FAIL | FAIL | FAIL |
| pi-sw2-p48 | ok | ok | FAIL | FAIL (not shown) | FAIL | FAIL | FAIL |

### ps1, 9 boards ([report](audits/2026-09-14-ps1.md); [pi9 with evidence](audits/2026-09-14-ps1-pi9.md))

| board | page | camera | terminal | poe status | ssh | upload | power cycle |
|---|---|---|---|---|---|---|---|
| pi2 | FAIL | FAIL | FAIL | ok (on) | FAIL | FAIL | FAIL |
| pi3 | FAIL | FAIL | ok | ok (on) | ok | FAIL | FAIL |
| pi5 | FAIL | FAIL | FAIL | ok (on) | FAIL | FAIL | FAIL |
| pi7 | FAIL | ok | FAIL | ok (on) | FAIL | FAIL | FAIL |
| pi9 | FAIL | ok | ok | ok (on) | ok | ok | ok |
| pi11 | FAIL | FAIL | FAIL | ok (on) | FAIL | FAIL | FAIL |
| pi13 | FAIL | FAIL | FAIL | ok (on) | FAIL | FAIL | FAIL |
| pi21 | FAIL | FAIL | FAIL | ok (on) | FAIL | FAIL | FAIL |
| pi23 | FAIL | FAIL | FAIL | ok (on) | FAIL | FAIL | FAIL |

**ps1 pi9 is the one board on either site where everything a user can do
works**, and it is the control for every negative result above: the same
code, on the same day, uploaded a bitstream through the form (landed on
`/pibup/success?pino=9`, the file 8s old by the Pi's own clock,
`openFPGALoader` exit 0 on screen, 2% of the picture changed and kept
changing), and pressed Reset (the status box said `set power off`, the
picture stuck at `05:02:57` for five readings, came back, and the Pi's
uptime was 2004s before and less than the wait after).

### The faults, by site

| Fault | Where | Found |
|---|---|---|
| **The Reset button does not power cycle the board.** Confirmed by the audit on pi-sw2-p42, the one welland board with a working terminal, so the uptime was read first: after the click the status box added only `socket connected / checking status: 42 / socket closed.` and never `set power`, and the picture kept advancing for 120s (`04:57:56` ... `04:58:09`). Same result on 2026-09-14 on p16, p37 and p42 by camera alone, controlled against ps1 pi7 in the same run. `toggle()` and `status()` share `mk_params()` and the SNMP helpers, and `/snmp/status` fails here too, so both directions of PoE control are almost certainly failing the same way. The user is told nothing: `dcws.js` calls `fetch('/snmp/toggle').then((error) => console.log(error))`, which has no error branch, so a failed power cycle looks exactly like a successful one. | welland | 2026-09-14 |
| **The web terminal cannot log in on 13 of 14 boards.** The wssh iframe shows its blank login form and `Authentication failed.`; no `/wssh/ws` socket is opened. pi-sw2-p42 reached a prompt in 12s on 2026-09-14 04:00 UTC, so whatever differs on p42 is the fix. It blocks every test that needs a shell. | welland | 2026-09-12 |
| **The upload form rejects a bitstream before Django sees it**: `413 Request Entity Too Large` from nginx for the 2.1 MB `counter_test/top.bit`, on all 14 boards. Nothing lands on the Pi (checked on p42, where the terminal works). ps1 accepts the same file. | welland | 2026-09-14 |
| **`Check PoE` never answers.** The status box shows `checking status: N` and nothing else on all 14 boards, because `POST /snmp/status` returns HTTP 500. ps1 answers `snmp: get power on`. | welland | 2026-09-12 |
| **The ssh command the page prints does not connect**: `ssh -p 2NN22 pi@welland.fpgas.online` prints nothing within 30s on all 14 boards (the per-board forward ports time out on IPv4 and IPv6, while :22 answers). | welland | 2026-09-12 |
| **Seven of nine boards have no picture**: the player reports `DEMUXER_ERROR_COULD_NOT_OPEN` on pi2, pi3, pi5, pi11, pi13, pi21 and pi23, and the page's "reset video player" button does not help. Only pi7 and pi9 show an advancing clock. | ps1 | 2026-09-13 |
| **Six of nine boards cannot be reached at all**: the web terminal's iframe says `Unable to connect to 10.21.0.1NN:22` and the printed ssh command gets `No route to host`, on pi2, pi5, pi11, pi13, pi21 and pi23. They are **powered but not responding**, not off: `Check PoE` says `power on` for every one of them. | ps1 | 2026-09-13 |
| **The page does not say what FPGA is fitted.** Every heading reads only `Accessing piN`; welland's read `Accessing pi-sw2-p37 -- Digilent Arty A7-35T`. A user cannot tell what hardware they are about to program. | ps1 | 2026-09-12 |
| **One visitor's half-typed command blocks every other visitor.** The web terminal and direct ssh both land in one shared tmux session per board. On 2026-09-14 pi7 had `sudo apt install pipx` sitting unrun on its prompt line for over an hour; every other visitor's terminal, and the printed ssh command, arrive at that line with no prompt to use. The suite refuses to press Enter into someone else's command, so pi7's terminal, upload and power-cycle cells all fail with that line quoted. | both (design) | 2026-09-14 |
| **The camera player sometimes fails to start** on a camera that is streaming fine: black video, `readyState 0`, `paused`, no error. The page's own "reset video player" button clears it; the audit marks such cells `ok (reset needed)` (1 of 11 live welland cameras on 2026-09-14; earlier samples were nearer one load in four). | both | 2026-09-13 |
| Running the pre-split monorepo build, so its pages differ from welland's | ps1 | known |

Note the reversal worth keeping in mind: **ps1 runs older code but is in
better health** in the parts that matter for using a board. Its web terminal
connects, its PoE status answers, its ssh forward ports are reachable, its
upload form accepts a bitstream, and its Reset button really cuts the power --
all five broken on welland. What ps1 lacks is boards: seven of nine have no
picture and six cannot be reached.

## Withdrawn

**"`POST /pibup/upload` returns 500 on both sites"** (2026-09-12) came from
a request made outside the browser, and it was wrong for ps1: on 2026-09-14
the audit uploaded `counter_test/top.bit` through the form on pi9 and landed
on the site's own success page, with the file on the Pi and the FPGA
programmed. On welland the form fails, but at nginx with a 413, before
Django is involved. The `cleaned_data['run']` reading of `pibup/views.py`
stands as a reading of the source; it is not what a user meets.

**"The browser must launch with `--autoplay-policy=no-user-gesture-required`
or the player never starts"** was in the spec, the plan and the README. On
2026-09-14 the page's picture came alive with no flag at all in all four
combinations tried -- Playwright's bundled Chromium and Google Chrome, each
headless and headed. The `<video>` is muted, and muted autoplay is allowed
under the default policy, as it is for a user. The original measurement was
taken through the one-in-four player-start bug listed above. The suite now
runs Google Chrome with a window and no launch flags, and refuses any other
browser.

**"Navigating between board pages kills the video player"** was reported on
2026-09-13 and is not a site fault. Playwright's bundled Chromium never
recovers once a player has failed -- pi7 live, pi9 live, pi2 dead, pi7 dead
again -- but real Chrome 145 recovers on the next page, and the only board
that stayed dead in Chrome was ps1 pi2, whose stream was 404ing anyway. The
fixture still opens each candidate in its own browser context, because doing
otherwise makes the suite blame boards for its own browser's state.

The suite fails loudly on any of these rather than skipping them. A suite that
quietly tolerated them would stop being evidence that the service works.

## On the reliability of these findings

Several entries above were first reported wrongly, and the pattern is worth
recording: every one came from an instrument that had not been validated
against the thing it claimed to measure. The clock reader called live cameras
frozen because it could not read grey on grey; a single camera sample called
working boards dead a quarter of the time; a stopped-picture check counted a
player seeking in its buffer as a board losing power; and a playlist fetch on
the server was reported as "the camera works".

The rule the suite now follows: a negative result is not evidence until the
same instrument has produced a positive one under control, in the same run.
That is how the welland power-cycle finding above was established, and it is
why it can be trusted where the earlier claims could not.
