"""Should this scheduled run test, or has a recent scheduled run already done so? (#16)

GitHub drops and delays `schedule` slots: the six-hourly cron ran about every
second slot, with gaps up to 19 hours (issue #16). The workflow is therefore
scheduled every 2 hours, and a scheduled run tests only when the last scheduled
run that tested started at least MIN_GAP ago. A dropped slot costs about 2
hours instead of 6. A dispatched run always tests.

Each run also names the six-hourly slot it serves (00, 06, 12, 18 UTC), so a
gap shows in the run summaries, not only by listing runs.

usage (in the workflow's plan job, with GH_TOKEN, GITHUB_REPOSITORY,
GITHUB_RUN_ID and GITHUB_EVENT_NAME set):
    python -m e2e.schedule_due
prints `due=true|false` and `slot=<ISO time>` for $GITHUB_OUTPUT, and writes
the reason to $GITHUB_STEP_SUMMARY.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone

MIN_GAP = timedelta(hours=5)
SLOT = timedelta(hours=6)
# A job that runs only when the run tests (it is skipped otherwise).
TESTING_JOB = "unit"


def slot_of(now: datetime) -> datetime:
    """The six-hourly slot (00/06/12/18 UTC) this time belongs to."""
    day = now.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    return day + SLOT * ((now - day) // SLOT)


def decide(now: datetime, last_tested: datetime | None) -> tuple[bool, str]:
    """(due, reason) for a scheduled run, from when the last scheduled run that tested started."""
    if last_tested is None:
        return True, "no earlier scheduled run that tested was found"
    age = now - last_tested
    if age >= MIN_GAP:
        return True, f"the last scheduled run that tested started {age} ago (>= {MIN_GAP})"
    return False, f"the last scheduled run that tested started {age} ago (< {MIN_GAP}); skipping"


def _gh(path: str) -> dict:
    out = subprocess.run(["gh", "api", path], capture_output=True, text=True)
    if out.returncode != 0:
        # Fail loud: a wrong answer here either skips a due run or doubles the load.
        raise SystemExit(f"gh api {path} failed ({out.returncode}): {out.stderr.strip()}")
    return json.loads(out.stdout)


def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def last_tested_start(repo: str, this_run: int) -> datetime | None:
    """Start of the newest earlier scheduled run whose testing job did not skip."""
    run = _gh(f"repos/{repo}/actions/runs/{this_run}")
    runs = _gh(f"repos/{repo}/actions/workflows/{run['workflow_id']}/runs?event=schedule&per_page=20")
    for r in sorted(runs["workflow_runs"], key=lambda r: r["run_started_at"] or r["created_at"], reverse=True):
        if r["id"] == this_run:
            continue
        jobs = _gh(f"repos/{repo}/actions/runs/{r['id']}/jobs")["jobs"]
        if any(j["name"] == TESTING_JOB and j["conclusion"] != "skipped" for j in jobs):
            return _parse(r["run_started_at"] or r["created_at"])
    return None


def main() -> int:
    now = datetime.now(timezone.utc)
    slot = slot_of(now)
    if os.environ.get("GITHUB_EVENT_NAME") != "schedule":
        due, reason = True, f"{os.environ.get('GITHUB_EVENT_NAME') or 'manual'} run: always tests"
    else:
        due, reason = decide(now, last_tested_start(os.environ["GITHUB_REPOSITORY"], int(os.environ["GITHUB_RUN_ID"])))
    print(f"due={'true' if due else 'false'}")
    print(f"slot={slot.isoformat()}")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a") as f:
            f.write(f"## Schedule\n\n- slot served: **{slot:%Y-%m-%d %H:%M} UTC**\n"
                    f"- {'testing' if due else 'not testing'}: {reason}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
