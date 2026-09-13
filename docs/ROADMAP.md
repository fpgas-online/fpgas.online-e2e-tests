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

The suite validates the *depth* of one path, not the breadth of identical
paths: if PoE control works on one board, it is not proven again on thirteen
more. One board is picked at random per run.

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

| Fault | Where | Found |
|---|---|---|
| **The web terminal cannot log in, on every board.** A full sweep of all 14 boards (pi-sw2-p16, p29, p33-p38, p42-p44, p46-p48) found not one that reached a shell prompt within 45s; all produced no terminal output whatsoever. In a browser the wssh iframe reports `Authentication failed.` then `socket closed.`, and no `/wssh/ws` WebSocket is opened at all. The same suite, same commit, same browser passes on ps1, so this is welland, not the client. It blocks every test that needs a shell -- which is most of them. | welland | 2026-09-12 |
| **`POST /snmp/status` returns HTTP 500.** The board page calls it on load ("Check PoE"), so the status box never learns the PoE state. PS1 answers `{state: on}`. | welland | 2026-09-12 |
| Per-board ssh forward ports unreachable from the internet (21622, 24222, ... time out on both IPv4 and IPv6, while :22 answers) | welland | 2026-09-12 |
| `POST /pibup/upload` returns 500: `pibup/views.py` reads `form.cleaned_data['run']` but `pibup/forms.py` defines no `run` field | both | 2026-09-12 |
| **Six of nine boards have no camera stream at all**: `/live/pi{3,5,11,13,21,23}.m3u8` all return HTTP 404, and the player reports `DEMUXER_ERROR_COULD_NOT_OPEN`. pi2, pi7 and pi9 serve 200 with a full segment window. | ps1 | 2026-09-13 |
| **The camera player fails to start on roughly one page load in six**, leaving a black video on a camera that is streaming fine: `readyState 0`, `paused`, no error, `src` still the `.m3u8` rather than a MediaSource blob. Measured over 19 loads of two healthy boards in fresh browser contexts (welland pi16 8/10, ps1 pi7 8/9); reloading fixes it. Not a cold-start effect -- failures do not cluster at a browser's first load. | both | 2026-09-13 |
| **The index names no FPGA type**, so a user cannot tell what hardware a board has before choosing it. welland prints `Digilent Arty A7-35T`; ps1 prints nothing. | ps1 | 2026-09-12 |
| Running the pre-split monorepo build, so its pages differ from welland's | ps1 | known |

**Five of PS1's nine boards are down entirely**, not merely missing a
terminal as first reported. A census on 2026-09-13 found pi5, pi11, pi13,
pi21 and pi23 failing at every layer at once: no shell prompt, no camera
stream on the server (`/live/...m3u8` 404), and their ssh forward ports
refusing or timing out. The hosts are off. pi3 has a working terminal and ssh
but no camera stream, so its camera service alone is down. Only pi7 and pi9
are fully healthy; pi2 is healthy server-side but its player would not start.

A user landing on one of the five gets a page where nothing works, with no
explanation.

**welland is the mirror image.** A census the same day found all 14 boards
listed with their FPGA types, all 14 camera playlists serving 200 with a full
segment window, and the cameras showing an advancing clock -- while all 14
web terminals failed to reach a prompt and all 14 per-board ssh ports timed
out. The hardware is there and visible; nothing you can log into works.

Note the reversal worth keeping in mind: **PS1 runs older code but is in better
health** in the parts that matter for logging in. Its web terminal connects on at least some boards, its PoE status
endpoint answers, and its ssh forward ports are reachable -- all three of
which are broken on welland.

The suite fails loudly on any of these rather than skipping them. A suite that
quietly tolerated them would stop being evidence that the service works.
