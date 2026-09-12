# Test roadmap

**Implemented:** power cycling, bitstream upload on an Arty, direct ssh
following the instructions on the board page.

The suite validates the *depth* of one path, not the breadth of identical
paths: if PoE control works on one board, it is not proven again on thirteen
more. One board is picked at random per run.

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
including its 256 KiB cap and 16-file eviction; and the legacy
`/fpgas/tt.html` route.

## Known production faults this suite reports

| Fault | Where | Found |
|---|---|---|
| **The web terminal cannot log in.** The wssh iframe reports `Authentication failed.` then `socket closed.`, and no `/wssh/ws` WebSocket is ever opened. PS1's terminal connects normally from the same browser, so this is welland-specific, not a client problem. This blocks every test that needs a shell. | welland | 2026-09-12 |
| **`POST /snmp/status` returns HTTP 500.** The board page calls it on load ("Check PoE"), so the status box never learns the PoE state. PS1 answers `{state: on}`. | welland | 2026-09-12 |
| Per-board ssh forward ports unreachable from the internet (21622, 24222, ... time out on both IPv4 and IPv6, while :22 answers) | welland | 2026-09-12 |
| `POST /pibup/upload` returns 500: `pibup/views.py` reads `form.cleaned_data['run']` but `pibup/forms.py` defines no `run` field | both | 2026-09-12 |
| `/fpgas/tt.html` returns 404 because the view hardcodes port 21 | both | 2026-09-12 |
| Running the pre-split monorepo build, so its pages differ from welland's | ps1 | known |

Note the reversal worth keeping in mind: **PS1 runs older code but is in better
health**. Its web terminal connects, its PoE status endpoint answers, and its
ssh forward ports are reachable -- all three of which are broken on welland.

The suite fails loudly on any of these rather than skipping them. A suite that
quietly tolerated them would stop being evidence that the service works.
