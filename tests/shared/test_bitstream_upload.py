"""Can a person upload a bitstream through the form and see it running?

The claim is the success page. The ground truth is that the file really landed
on the Pi at the right size, that openFPGALoader really programmed the part,
and that the LEDs visibly changed and are now counting.

Known limitation: counter_test/top.bit is the same bitstream the "Blink LEDs"
button loads, so the camera proves "the LEDs changed and are counting" but not
"this upload is what is running". A distinctive design from
fpgas.online-test-designs closes that gap later.
"""

from pathlib import Path

import pytest

from e2e.camera import difference

BITSTREAM = Path(__file__).parents[2] / "fixtures" / "counter_test" / "top.bit"
REMOTE = "Uploads/top.bit"
LED_REGION = (0.0, 0.55, 1.0, 0.45)


def _led_difference(a, b) -> float:
    return difference(a, b, region=LED_REGION)


@pytest.mark.live
def test_uploaded_bitstream_programs_the_arty_and_changes_the_leds(board_page, evidence):
    session = board_page("arty")
    page, terminal, camera = session.page, session.terminal, session.camera

    camera.wait_until_live(timeout=60)
    before = camera.shot()

    page.set_input_files("#upform input[type=file]", str(BITSTREAM))
    page.click("#upform input[type=submit]")
    page.wait_for_load_state("domcontentloaded")

    evidence.claim(
        "the upload form reports success",
        "uploaded" in page.content().lower(),
        detail=f"landed on {page.url} showing: {page.content()[:400]!r}",
    )

    page.go_back()
    terminal.reset()
    terminal.wait_for_prompt()

    listing = terminal.run(f"ls -l {REMOTE}")
    shown, detail = listing.shows(str(BITSTREAM.stat().st_size))
    evidence.ground_truth("the bitstream really landed on the Pi at the right size", shown, detail=detail)

    programming = terminal.run(f"openFPGALoader -b arty {REMOTE}", timeout=180)
    status = terminal.exit_status()
    evidence.ground_truth(
        "openFPGALoader programmed the FPGA",
        status == 0,
        detail=f"exit status {status}; output: {programming.text[-400:]!r}",
    )

    camera.wait_until_live(timeout=60)
    after = camera.shot()
    changed = _led_difference(before, after)
    evidence.ground_truth(
        "the LEDs look different from before the upload",
        changed > 0.02,
        detail=f"LED-region difference {changed:.4f}",
    )

    later = camera.shot()
    counting = _led_difference(after, later)
    evidence.ground_truth(
        "the LEDs are visibly counting, not frozen",
        counting > 0.005,
        detail=f"LED-region difference across two shots {counting:.4f}",
    )
