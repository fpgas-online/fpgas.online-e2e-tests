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


def test_a_false_claim_raises_with_the_description_and_detail():
    log = EvidenceLog()
    with pytest.raises(AssertionError) as excinfo:
        log.claim("status box says power off", False, detail="box was empty")
    assert "status box says power off" in str(excinfo.value)
    assert "box was empty" in str(excinfo.value)


def test_a_false_ground_truth_raises():
    log = EvidenceLog()
    with pytest.raises(AssertionError):
        log.ground_truth("uptime went backwards", False)


def test_a_failed_assertion_is_still_recorded_so_the_summary_shows_it():
    log = EvidenceLog()
    with pytest.raises(AssertionError):
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
