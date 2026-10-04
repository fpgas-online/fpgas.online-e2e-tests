"""The `disruptive` marker: skipped unless --disruptive, in one place (tests/conftest.py).

Run in a nested pytest (pytester) whose conftest reuses the suite's own option
and collection hook, so what is exercised is the real logic.
"""

import pytest

pytest_plugins = ["pytester"]

CONFTEST = """
from tests.conftest import pytest_addoption, pytest_collection_modifyitems  # noqa: F401
"""

TESTS = """
import pytest

def test_plain():
    pass

@pytest.mark.disruptive
def test_cuts_power():
    pass

@pytest.mark.live
@pytest.mark.disruptive
def test_reprograms_the_fpga():
    pass
"""


@pytest.fixture
def nested(pytester):
    pytester.makeconftest(CONFTEST)
    pytester.makeini("[pytest]\nmarkers =\n    live: x\n    disruptive: x\naddopts = -ra --strict-markers\n")
    pytester.makepyfile(TESTS)
    return pytester


def test_without_the_option_disruptive_tests_are_skipped_with_the_reason_and_never_run(nested):
    result = nested.runpytest("-v", "-p", "no:playwright")
    result.assert_outcomes(passed=1, skipped=2)
    result.stdout.fnmatch_lines(
        [
            "*::test_plain PASSED*",
            "*::test_cuts_power SKIPPED*",
            "*::test_reprograms_the_fpga SKIPPED*",
            "SKIPPED [[]1[]] *:6: needs --disruptive",
            "SKIPPED [[]1[]] *:10: needs --disruptive",
        ]
    )


def test_with_the_option_the_disruptive_tests_run(nested):
    result = nested.runpytest("--disruptive", "-p", "no:playwright")
    result.assert_outcomes(passed=3, skipped=0)


def test_the_option_is_off_by_default_and_the_reason_is_the_audits(pytester):
    from e2e.audit import NEEDS_DISRUPTIVE

    assert NEEDS_DISRUPTIVE == "needs --disruptive"


def test_the_real_shared_tests_carry_the_marker(pytestconfig):
    """The two shared tests that change a board are the marked ones."""
    import tests.shared.test_bitstream_upload as upload
    import tests.shared.test_board_page_basics as basics
    import tests.shared.test_direct_ssh as ssh
    import tests.shared.test_power_cycle as power

    def marked(fn):
        return any(m.name == "disruptive" for m in getattr(fn, "pytestmark", []))

    assert marked(upload.test_uploaded_bitstream_programs_the_fpga_and_changes_the_leds)
    assert marked(power.test_reset_button_power_cycles_the_board)
    assert not marked(basics.test_a_board_page_gives_you_a_live_camera_and_a_working_terminal)
    assert not marked(ssh.test_ssh_instructions_on_the_page_let_you_log_in)
