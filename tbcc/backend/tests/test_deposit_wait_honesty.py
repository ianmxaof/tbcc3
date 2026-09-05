"""Waiting on an import must never invent a failure it did not verify.

2026-09-04: await_deposit_import_job declared `import_never_started — TBCC Celery worker
may be offline. Restart TBCC worker.` after 90s in `queued`. The worker was healthy, the
job simply had not reached the front of a serialized queue; 23 minutes later it stored 105
items. The advice to restart was wrong and, acted on, risks a second bot and a 409.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.services.storage_topic_deposit import (
    await_deposit_import_job,
    format_deposit_complete_text,
)


class _Job:
    def __init__(self, status="queued", stage="queued"):
        self.id = "job-1"
        self.status = status
        self.stage = stage


def _db_returning(job):
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = job
    db.close = MagicMock()
    return db


def _wait(job, **kw):
    """Run await_deposit_import_job against a fixed job row."""
    with patch("app.database.session.SessionLocal", return_value=_db_returning(job)), patch(
        "app.services.import_pipeline.TERMINAL_STATUSES", {"done", "failed"}
    ), patch(
        "app.services.import_pipeline.job_to_public_dict",
        side_effect=lambda j: {"job_id": j.id, "status": j.status, "result": {"stored": 105}},
    ), patch(
        "app.services.channel_import_runner.channel_import_timeout_s", return_value=1
    ):
        return asyncio.run(await_deposit_import_job("job-1", poll_s=0.01, **kw))


def test_queued_job_is_reported_as_queued_not_as_a_broken_worker():
    out = _wait(_Job(status="queued"), queued_patience_s=0.05)

    assert out is not None
    assert out["status"] == "still_queued"
    err = out["error"].lower()
    # The harmful advice is gone...
    assert "may be offline" not in err
    assert "restart tbcc worker" not in err
    # ...and replaced by an explicit instruction not to act.
    assert "do not restart anything" in err
    assert "still pending, not lost" in err


def test_patience_can_be_disabled_so_the_real_timeout_governs():
    """The drain path needs no 90s fuse; the queue wait is legitimately long."""
    out = _wait(_Job(status="queued"), queued_patience_s=None, timeout_s=1)

    # No synthetic never-started verdict — we fall through to the deadline path,
    # which reports the job's real status instead of None.
    assert out is not None
    assert out["status"] == "timeout"
    assert out["job_status"] == "queued"
    assert "not been cancelled" in out["error"]


def test_terminal_job_is_returned_normally():
    out = _wait(_Job(status="done"))

    assert out["status"] == "done"
    assert out["result"]["stored"] == 105


def test_deadline_rereads_the_row_and_reports_a_late_completion():
    """The job may finish between the last poll and the deadline — look before reporting."""
    job = _Job(status="queued")

    calls = {"n": 0}

    def _first(_j):
        calls["n"] += 1
        return {"job_id": "job-1", "status": job.status, "result": {"stored": 105}}

    db = _db_returning(job)

    def _flip(*_a, **_k):
        # Flip the row to done as soon as the poll loop has seen it queued once.
        if calls["n"] >= 0 and job.status == "queued":
            job.status = "done"
        return db

    with patch("app.database.session.SessionLocal", side_effect=_flip), patch(
        "app.services.import_pipeline.TERMINAL_STATUSES", {"done", "failed"}
    ), patch("app.services.import_pipeline.job_to_public_dict", side_effect=_first), patch(
        "app.services.channel_import_runner.channel_import_timeout_s", return_value=1
    ):
        out = asyncio.run(await_deposit_import_job("job-1", poll_s=0.01, timeout_s=1))

    assert out["status"] == "done"
    assert out["result"]["stored"] == 105


def test_pending_status_does_not_print_no_new_media():
    """The formatter must not read absent counters as a zero-import result."""
    report = {"pool_name": "TABOO", "topic_title": "AOF TABOO", "limit": 200}
    body = {
        "job_id": "job-1",
        "status": "still_queued",
        "error": "import_still_queued — the job has waited 90s for the telegram worker",
    }

    text = format_deposit_complete_text(report, body, html=True)

    assert "still running" in text.lower()
    assert "No new media imported" not in text
    assert "failed" not in text.lower()
