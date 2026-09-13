import pytest

from e2e.evidence import EvidenceKind, EvidenceLog


def test_a_true_claim_is_recorded_as_a_claim():
    log = EvidenceLog()
    log.claim("status box says power off", True)
    assert [e.kind for e in log.entries] == [EvidenceKind.CLAIM]
    assert log.has_ground_truth is False


def test_a_true_ground_truth_is_recorded_and_satisfies_the_requirement():
    log = EvidenceLog()
    log.ground_truth("uptime went backwards", True, detail="U0=812 U1=41")
    assert log.has_ground_truth is True


def test_a_false_claim_is_recorded_with_its_description_and_detail():
    """It is reported at the end of the test, not raised where it happened."""
    log = EvidenceLog()
    log.claim("status box says power off", False, detail="box was empty")
    failed = log.failures[0]
    assert failed.description == "status box says power off"
    assert failed.detail == "box was empty"


def test_a_false_ground_truth_raises():
    log = EvidenceLog()
    with pytest.raises(AssertionError):
        log.ground_truth("uptime went backwards", False)


def test_a_failed_assertion_is_still_recorded_so_the_summary_shows_it():
    log = EvidenceLog()
    log.claim("nope", False)
    assert len(log.entries) == 1
    assert log.entries[0].passed is False


def test_summary_lists_every_entry_with_its_kind():
    log = EvidenceLog()
    log.claim("a claim", True)
    log.ground_truth("a fact", True)
    summary = log.summary()
    assert "[claim] a claim" in summary
    assert "[ground truth] a fact" in summary


def test_a_failed_claim_does_not_stop_the_test():
    """The test must still get as far as observing reality.

    On welland the PoE status endpoint 500s, so the status box never reports
    the switch. Raising there aborted the power-cycle test before it could
    watch the board actually reboot -- reporting the first thing checked
    instead of what the user experiences.
    """
    log = EvidenceLog()
    log.claim("the status box reported the switch", False, detail="box was silent")
    log.ground_truth("the board really rebooted", True)

    assert [e.description for e in log.failures] == ["the status box reported the switch"]
    assert log.has_ground_truth


def test_a_failed_ground_truth_still_raises():
    """Once an observation of reality has failed, carrying on proves nothing."""
    log = EvidenceLog()
    with pytest.raises(AssertionError):
        log.ground_truth("the camera showed a live picture", False)
