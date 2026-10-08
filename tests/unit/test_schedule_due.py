"""The two-hourly schedule tests only when the last tested scheduled run is 5 hours old (#16)."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

from e2e.schedule_due import MIN_GAP, decide, slot_of

UTC = timezone.utc
WORKFLOW = Path(__file__).resolve().parents[2] / ".github/workflows/e2e.yml"


def test_the_slot_is_the_six_hourly_one():
    assert slot_of(datetime(2026, 10, 7, 13, 7, tzinfo=UTC)) == datetime(2026, 10, 7, 12, 0, tzinfo=UTC)
    assert slot_of(datetime(2026, 10, 7, 5, 35, tzinfo=UTC)) == datetime(2026, 10, 7, 0, 0, tzinfo=UTC)
    assert slot_of(datetime(2026, 10, 7, 18, 0, tzinfo=UTC)) == datetime(2026, 10, 7, 18, 0, tzinfo=UTC)


def test_a_run_is_due_when_nothing_tested_before():
    assert decide(datetime(2026, 10, 7, 12, tzinfo=UTC), None)[0] is True


def test_a_run_skips_within_five_hours_of_the_last_tested_run():
    now = datetime(2026, 10, 7, 12, tzinfo=UTC)
    assert decide(now, now - timedelta(hours=2))[0] is False
    assert decide(now, now - MIN_GAP + timedelta(minutes=1))[0] is False


def test_a_run_tests_from_five_hours_on():
    now = datetime(2026, 10, 7, 12, tzinfo=UTC)
    assert decide(now, now - MIN_GAP)[0] is True
    # the 19-hour gap of issue #16 is caught at the next two-hourly start
    assert decide(now, now - timedelta(hours=19))[0] is True


def test_the_workflow_runs_every_two_hours_and_gates_the_tests_on_the_plan():
    text = WORKFLOW.read_text()
    assert '- cron: "0 */2 * * *"' in text
    assert '"0 */6 * * *"' not in text
    assert "due: ${{ steps.due.outputs.due }}" in text
    assert "run: python3 -m e2e.schedule_due >> \"$GITHUB_OUTPUT\"" in text
    # every job that tests is gated on the plan's answer
    assert text.count("needs.plan.outputs.due == 'true'") == 3
    assert "    needs: plan\n    if: ${{ needs.plan.outputs.due == 'true' }}" in text
