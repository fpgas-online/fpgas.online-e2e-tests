"""The two-hourly schedule tests only when the last tested scheduled run is 5 hours old (#16)."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

from e2e import schedule_due
from e2e.schedule_due import MIN_GAP, decide, last_tested_start, slot_of

UTC = timezone.utc
WORKFLOW = Path(__file__).resolve().parents[2] / ".github/workflows/e2e.yml"


def test_the_slot_is_the_six_hourly_one():
    assert slot_of(datetime(2026, 10, 7, 13, 7, tzinfo=UTC)) == datetime(2026, 10, 7, 12, 0, tzinfo=UTC)
    # early by GitHub's clock drift: still the 06:00 slot (issue #16's table)
    assert slot_of(datetime(2026, 10, 7, 5, 35, tzinfo=UTC)) == datetime(2026, 10, 7, 6, 0, tzinfo=UTC)
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


def test_last_tested_start_skips_runs_that_did_not_test(monkeypatch):
    runs = {"workflow_runs": [
        {"id": 5, "run_started_at": "2026-10-07T12:00:00Z", "created_at": "2026-10-07T12:00:00Z"},  # this run
        {"id": 4, "run_started_at": "2026-10-07T10:00:00Z", "created_at": "2026-10-07T10:00:00Z"},  # skipped
        {"id": 3, "run_started_at": "2026-10-07T08:00:00Z", "created_at": "2026-10-07T08:00:00Z"},  # cancelled
        {"id": 2, "run_started_at": "2026-10-07T06:01:00Z", "created_at": "2026-10-07T06:01:00Z"},  # tested
    ]}
    jobs = {4: "skipped", 3: "cancelled", 2: "failure"}

    def fake_gh(path):
        if path.endswith("/runs/5"):
            return {"workflow_id": 77}
        if "/workflows/77/runs" in path:
            return runs
        run_id = int(path.split("/runs/")[1].split("/")[0])
        return {"jobs": [{"name": "plan", "conclusion": "success"}, {"name": "unit", "conclusion": jobs[run_id]}]}

    monkeypatch.setattr(schedule_due, "_gh", fake_gh)
    assert last_tested_start("o/r", 5) == datetime(2026, 10, 7, 6, 1, tzinfo=UTC)


def test_a_run_under_way_counts_as_testing(monkeypatch):
    def fake_gh(path):
        if path.endswith("/runs/9"):
            return {"workflow_id": 1}
        if "/workflows/1/runs" in path:
            return {"workflow_runs": [{"id": 8, "run_started_at": "2026-10-07T11:00:00Z", "created_at": "x"}]}
        return {"jobs": [{"name": "unit", "conclusion": None}]}

    monkeypatch.setattr(schedule_due, "_gh", fake_gh)
    assert last_tested_start("o/r", 9) == datetime(2026, 10, 7, 11, 0, tzinfo=UTC)
