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
    uv run pytest tests/shared --site welland --disruptive -k power_cycle   # on a desktop: watch it

`--site` takes `welland` or `ps1`. Each run prints the random seed it used, so
a failure can be replayed against the same board with `--seed`.

## What runs on the schedule, and what `--disruptive` adds

The workflow runs every six hours on one randomly chosen board per site, and
it never power-cycles or reprograms a board unattended. Tests marked
`@pytest.mark.disruptive` are skipped unless `--disruptive` is given (one hook
in `tests/conftest.py`), with the reason "needs --disruptive", listed in the
pytest summary as skipped, never as passed. Two tests carry the marker: the
bitstream upload (reprograms the FPGA) and the power cycle (Reset: PoE off,
the Pi reboots, the video is gone for minutes, and on some boards the camera
focus is lost until someone restores it). The scheduled run and a plain manual
dispatch pass no `--disruptive`; tick the `disruptive` box on the "Run
workflow" form to pass it to the `shared` job. The audit has its own
`audit_disruptive` box.

What a scheduled run still does to the chosen board: it loads the index page
and the board's page and opens the page's web terminal and camera (reads);
reaches the camera by the page's own "reset video player" and Play buttons if
the player is stuck (nothing on the Pi); types `hostname` and `uptime -p`
into the shared tmux session, which land in that shell's history and on the
screen of anyone watching; and makes one ssh login with the banner's
password, typing `hostname`, which is a second client on the same tmux
session. It does not click "Check PoE", Reset, or the upload form.

The suite does not assume it has the terminal to itself. Typing appends to
whatever is on the shell's line and Enter runs it, so before typing, in the
web terminal and after the ssh login, the suite reads the screen. Whether a
visitor can be on our line at all is not shown by this repo: the Pis'
`zprofile` (fpgas.online-setup-pi, `onpi/tmux`) says each login is a new
window in a shared tmux session group, which would give our login a fresh
prompt, but the suite has not observed which of the two happens. The guard
costs nothing, so it stays. What it does, in plain terms:

- **A visitor is using the terminal: the test is skipped, nothing is typed.**
  Only this skips: the shell's last prompt line has anything after it other
  than the cursor block (a lone `|`, `_`, `[` or `l` counts as text), with
  at most unremarkable output under it, which is what a half-typed or
  running command looks like. The skip reason reads "a visitor is using the
  terminal: ..." and quotes the screen it was judged from; `-ra` lists it. This
  applies in the `board_page` fixture, in the web terminal, and after the ssh
  login. In the audit the cell reads "skipped" with that reason.
- **Everything else that is not a free line fails, quoting the screen.** No
  prompt line at all (a login form, "Authentication failed.", a prompt that
  was there moments ago and is gone), and text under the prompt that is a
  closed session, an error or a system message ("Connection to ... closed",
  "Stale file handle", "Input/output error", a broadcast, a kernel line,
  "Read-only file system") or that the suite does not recognise. When in
  doubt it fails: a skip hides a broken board, a failure gets looked at.
- **The camera is checked before the terminal**, so a busy terminal cannot
  hide a board whose picture is dead.
- **A skip never hides a failure**: if the test had already recorded evidence
  that did not hold, it fails instead of skipping.
- The cursor is never read by OCR. It is found in the screenshot (xterm's
  filled block, or the hollow outline when the terminal is unfocused) and
  painted out first; a cursor that blinks is looked for again. Ink in the cell
  just left of it is a typed character even if OCR dropped it, so that line is
  busy. If typed text touches the cursor so that no separate block is found,
  text that reads the same in every look, on the last prompt row with nothing
  under it that reads as a fault, is a visitor (a skip quoting the screen);
  text that changes between looks is a failure.
- The tmux status line is ignored. It is the last row and must have the whole
  shape (session number, at least one `<digit>:<name>` window, host, clock);
  a clock at the end of a line is not enough, and a row that reads as a fault
  is never taken for it. OCR dropping brackets or flags, or reading digits as
  lookalikes (`O`, `l`, `S`, `B`, `Z`), is tolerated. If the row is mangled
  beyond that the result is a failure, not a skip.

What still fails by design, and why. The rule is "when in doubt, fail": a skip
hides a broken board and a failure gets looked at. So these fail and do not
skip: a full-screen program (a REPL, `less`, `htop`) or a wrapped prompt, where
no prompt row is on screen; text under an empty prompt the suite does not
recognise; and a visitor's command whose output under the typed line contains
an error pattern ("error", "failed", "Permission denied", ...). Each login
should get its own tmux window, so these should be rare; if one recurs on a
board, look at the screen quoted in the failure.

**A board that is skipped as busy on every scheduled run needs a look**: a
suite that always skips tests nothing. Read the screen quoted in the skip
reason (it is in the job log and the `-ra` summary): it is either a real
long-running command, or a prompt this suite misreads.

The read can be fooled in both directions by OCR; the design accepts a
spurious skip or failure but not a typed command. A visitor who starts typing
in the few milliseconds between the look and the keystrokes is not detected.

## Auditing a whole site

    xvfb-run -a uv run pytest tests/audit --site ps1 -s               # changes nothing on the boards
    xvfb-run -a uv run pytest tests/audit --site ps1 -s --disruptive  # also uploads and power-cycles

Where a test picks one board and stops at the first thing wrong, the audit
visits every board the index lists and runs the same journeys on each,
producing one row per board:

    ### ps1: 9 boards, audited 2026-09-14T04:10:22Z   (illustrative hostnames)
    board  page  camera             terminal  poe status  ssh   upload  power cycle
    HOST2  ok    FAIL               FAIL      ok (on)     FAIL  FAIL    FAIL
    HOST7  ok    ok (reset needed)  ok        ok (on)     ok    FAIL    ok
    ...

    why:
      pi2 camera: ...

The table is printed at the end, written to `<output>/audit-<site>.md`, and
on GitHub appended to the job summary. A cell passes only if every
observation in that journey held; the reasons under the table quote what was
seen. The test fails if any cell failed.

These are public boards that other people may be using, so the upload and the
power cycle (which reprograms the FPGA, cuts PoE and drops the video for
minutes) run only with `--disruptive`; without it those two cells read
"skipped" and the reason ("needs --disruptive") is listed under the table.
`--quick` is still accepted and changes nothing: leaving them out is the
default now. The audit is not on the six-hourly schedule: run it from the
Actions page with the "audit" box ticked (and "audit_disruptive" as well to
include the upload and power cycle), or by hand. `--boards
HOSTNAME,HOSTNAME` (hostnames as the index lists them) narrows it; see "Which
boards a run may touch". A board whose FPGA type has no bitstream in this repo (every Acorn)
shows "skipped" in the upload column.

## Which boards a run may touch

- `--boards HOSTNAME[,HOSTNAME...]` (hostnames as the index lists them)
  restricts the whole run to those boards. The audit audits only them; the
  shared tests choose only among the named boards that the site lists, and
  fail, naming them, if it lists none. With `--boards` no test opens any other
  board's page.
- `--disruptive` (the bitstream upload and the power cycle) never chooses a
  board: it needs `--boards`, and without it the run is refused before any
  test starts. Nothing disruptive runs on a board you did not name.
- Some devices must never be disrupted, even when named. They are listed in
  `e2e/protected_boards.toml` by the Pi's serial number, with the label name
  and the reason, never by port or hostname. At run time the serial is looked
  up against the site's public registry (`/fleet/`), so a protected device is
  recognised under whatever hostname it has that day. A disruptive action on a
  protected device is refused with a failure naming its label and reason; in
  the audit its upload and power cycle cells fail with the same words.
- The registry is read afresh immediately before each disruptive action (one
  GET), not once per run, so a device that changed hostname since the run began
  is judged by what it is now. If it cannot be read, or a named board is not
  in it, its identity is unknown, and the disruptive action fails rather than
  going ahead.
- Tests that only do what a visitor does are unaffected by the protected list.

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

## Known failures

`e2e/known_failures.py` is a small table of (site, test) pairs that are known to
fail on that site, each with the issue that tracks it. Each entry is applied as a
strict expected failure, for one kind of failure only (named by the entry's exception), so any
other failure of the same test still fails the run, and so
does the test starting to pass: that is the cue to remove the entry. The entry is
removed when the linked issue is fixed. The table is empty at present. The audit is not affected: it reports
the failure and its reason as it always did.

## What it tests

See [docs/ROADMAP.md](docs/ROADMAP.md).

These tests run against the **live production** service. Without
`--disruptive` their side effects are the small ones listed under "What runs
on the schedule"; with it, a board gets power-cycled and an FPGA gets
reprogrammed, so use it by hand and not on a schedule. One board is picked at
random per run.

## Licence

Apache 2.0
