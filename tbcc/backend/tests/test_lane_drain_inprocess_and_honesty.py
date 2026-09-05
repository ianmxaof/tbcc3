"""Lane drain: run the import in-process, and never report a failure it did not verify.

Background (2026-09-04): a drain dispatched its import job onto the same solo telegram
queue it was occupying, waited 90 seconds, then reported
"import_never_started — TBCC Celery worker may be offline. Restart TBCC worker."
The job was picked up 23 minutes later and stored 105 items. The drain reported 0.
"""

import asyncio
import json
import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.services import storage_lane_drain as drain


# --------------------------------------------------------------------------- lock honesty


class _FakeRedis:
    def __init__(self):
        self.store: dict[str, str] = {}
        self.ttls: dict[str, int] = {}

    def get(self, k):
        return self.store.get(k)

    def set(self, k, v, nx=False, ex=None):
        if nx and k in self.store:
            return None
        self.store[k] = v
        if ex:
            self.ttls[k] = int(ex)
        return True

    def delete(self, k):
        self.store.pop(k, None)
        self.ttls.pop(k, None)

    def ttl(self, k):
        return self.ttls.get(k, -1)


@pytest.fixture
def fake_redis(monkeypatch):
    r = _FakeRedis()
    monkeypatch.setattr(drain, "_redis", lambda: r)
    return r


def test_lock_starts_as_queued_not_running(fake_redis):
    """A claimed lock means 'queued', not 'work is happening'."""
    fake_redis.set(drain._lock_key("taboo"), drain._lock_payload("tok", "queued"))

    state = drain.lane_drain_state("taboo")

    assert state["held"] is True
    assert state["state"] == "queued"
    assert state["stale"] is False
    assert drain.is_lane_draining("taboo") is True


def test_running_lock_goes_stale_when_the_heartbeat_ages_out(fake_redis):
    old = json.dumps(
        {"token": "tok", "state": "running", "ts": time.time() - 10_000, "iterations": 3, "stored": 5}
    )
    fake_redis.set(drain._lock_key("taboo"), old)

    state = drain.lane_drain_state("taboo")

    assert state["state"] == "stale"
    assert state["stale"] is True
    assert state["iterations"] == 3


def test_fresh_running_lock_is_not_stale(fake_redis):
    fake_redis.set(drain._lock_key("taboo"), drain._lock_payload("tok", "running", iterations=2))

    assert drain.lane_drain_state("taboo")["state"] == "running"


def test_legacy_bare_token_lock_is_still_readable(fake_redis):
    """Locks written before the heartbeat format must not crash the probe."""
    fake_redis.set(drain._lock_key("taboo"), "plain-token-abc")

    state = drain.lane_drain_state("taboo")

    assert state["held"] is True
    assert state["state"] == "unknown"
    assert state["stale"] is False


def test_no_lock_reads_as_idle(fake_redis):
    assert drain.lane_drain_state("taboo") == {
        "lane_key": "taboo",
        "held": False,
        "state": "idle",
    }
    assert drain.is_lane_draining("taboo") is False


# ------------------------------------------------------------------- in-process import


def _run_drain(fake_redis, *, job_results, token="tok"):
    """Drive run_lane_drain with a scripted sequence of import outcomes."""
    fake_redis.set(drain._lock_key("taboo"), drain._lock_payload(token, "queued"), ex=2100)

    deposits = []

    def _queue_deposit(db, **kw):
        deposits.append(kw)
        return {"ok": True, "job_id": f"job{len(deposits)}", "index_only": True}

    results = list(job_results)

    async def _inline(job_id):
        return results.pop(0) if results else {"status": "done", "stored": 0, "skipped_duplicate": 0, "messages_scanned": 0}

    with patch.object(drain, "_run_import_job_inline", side_effect=_inline), patch(
        "app.services.storage_topic_deposit.queue_storage_topic_deposit",
        side_effect=_queue_deposit,
    ), patch("app.database.session.SessionLocal", MagicMock()), patch(
        "app.services.hub_intake_policy.hub_master_auto_approve_enabled", return_value=True
    ), patch(
        "app.services.storage_deposit_control.get_deposit_limit", return_value=200
    ), patch(
        "app.services.storage_deposit_control.get_deposit_media_types", return_value="both"
    ), patch(
        "app.services.storage_hub_op_status.edit_hub_op_status", MagicMock()
    ):
        out = asyncio.run(
            drain.run_lane_drain(
                "taboo",
                token=token,
                chat_id=-100,
                message_thread_id=2919,
                status_message_id=None,
            )
        )
    return out, deposits


def test_drain_does_not_dispatch_its_import_to_its_own_queue(fake_redis):
    """enqueue=False is the whole fix — dispatching self-queues behind the drain."""
    _out, deposits = _run_drain(
        fake_redis,
        job_results=[{"status": "done", "stored": 0, "skipped_duplicate": 0, "messages_scanned": 0}],
    )

    assert deposits, "deposit was never attempted"
    assert deposits[0]["enqueue"] is False


def test_drain_counts_what_the_import_actually_stored(fake_redis):
    """The regression: 105 stored had to stop being reported as 0."""
    out, _ = _run_drain(
        fake_redis,
        job_results=[
            {"status": "done", "stored": 105, "skipped_duplicate": 79,
             "messages_scanned": 207, "oldest_scanned_message_id": 74600},
            {"status": "done", "stored": 0, "skipped_duplicate": 0, "messages_scanned": 0},
        ],
    )

    assert out["total_stored"] == 105
    assert out["total_skipped_duplicate"] == 79
    assert out["stop_reason"] == "drained"
    assert out["iterations"] == 2


def test_drain_reads_counters_nested_under_result_too(fake_redis):
    """The runner returns flat counters; an ImportJob row nests them under `result`."""
    out, _ = _run_drain(
        fake_redis,
        job_results=[
            {"status": "done", "result": {"stored": 12, "skipped_duplicate": 3,
                                          "messages_scanned": 15,
                                          "oldest_scanned_message_id": 900}},
            {"status": "done", "result": {"stored": 0, "skipped_duplicate": 0,
                                          "messages_scanned": 0}},
        ],
    )

    assert out["total_stored"] == 12
    assert out["total_skipped_duplicate"] == 3


def test_drain_loops_until_the_cursor_exhausts_the_topic(fake_redis):
    out, deposits = _run_drain(
        fake_redis,
        job_results=[
            {"status": "done", "stored": 10, "skipped_duplicate": 0,
             "messages_scanned": 12, "oldest_scanned_message_id": 900},
            {"status": "done", "stored": 0, "skipped_duplicate": 4,
             "messages_scanned": 4, "oldest_scanned_message_id": 880},
            {"status": "done", "stored": 0, "skipped_duplicate": 0, "messages_scanned": 0},
        ],
    )

    assert len(deposits) == 3
    assert out["total_stored"] == 10
    assert out["stop_reason"] == "drained"


def test_drain_marks_lock_running_on_first_batch(fake_redis):
    seen_states = []

    async def _inline_capture(job_id):
        lock = drain.read_lane_drain_lock("taboo")
        seen_states.append(lock and lock.get("state"))
        return {"status": "done", "stored": 0, "skipped_duplicate": 0, "messages_scanned": 0}

    fake_redis.set(drain._lock_key("taboo"), drain._lock_payload("tok", "queued"), ex=2100)
    with patch.object(drain, "_run_import_job_inline", side_effect=_inline_capture), patch(
        "app.services.storage_topic_deposit.queue_storage_topic_deposit",
        side_effect=lambda db, **kw: {"ok": True, "job_id": "j1"},
    ), patch("app.database.session.SessionLocal", MagicMock()), patch(
        "app.services.hub_intake_policy.hub_master_auto_approve_enabled", return_value=True
    ), patch(
        "app.services.storage_deposit_control.get_deposit_limit", return_value=10
    ), patch(
        "app.services.storage_deposit_control.get_deposit_media_types", return_value="both"
    ), patch(
        "app.services.storage_hub_op_status.edit_hub_op_status", MagicMock()
    ):
        asyncio.run(
            drain.run_lane_drain(
                "taboo", token="tok", chat_id=-100, message_thread_id=2919, status_message_id=None
            )
        )

    assert seen_states == ["running"]


def test_cancelled_lock_stops_the_loop(fake_redis):
    """Clearing the lock is the cancel mechanism and must still work."""
    fake_redis.set(drain._lock_key("taboo"), drain._lock_payload("other-token", "running"))

    # Our token no longer matches the stored lock, so the loop must stop before any work.
    with patch.object(drain, "_run_import_job_inline"), patch(
        "app.services.storage_topic_deposit.queue_storage_topic_deposit"
    ), patch("app.database.session.SessionLocal", MagicMock()), patch(
        "app.services.storage_hub_op_status.edit_hub_op_status", MagicMock()
    ):
        out = asyncio.run(
            drain.run_lane_drain(
                "taboo", token="tok", chat_id=-100, message_thread_id=2919, status_message_id=None
            )
        )

    assert out["stop_reason"] == "cancelled"
    assert out["iterations"] == 0
