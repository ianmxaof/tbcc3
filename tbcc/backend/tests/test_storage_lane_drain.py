"""Drain-this-lane stop conditions and cancellation.

Cursor lock (Phase 1 authorization): do NOT stop on the first batch with stored==0
alone if skipped_duplicate>0 — only stop when a batch is fully empty (stored==0 AND
skipped_duplicate==0), or a safety cap fires.

Phase 3 (2026-09-04): the drain no longer dispatches its import onto the telegram queue
it is occupying and then polls for it. It runs the job in-process via
_run_import_job_inline, which is what these tests now stub.
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

from app.services import storage_lane_drain as drain


class _FakeDBCtx:
    def __enter__(self):
        return MagicMock()

    def __exit__(self, *exc):
        return False


def _fake_session_local():
    return _FakeDBCtx()


def _patch_common(monkeypatch, *, auto_approve: bool = True):
    monkeypatch.setattr("app.database.session.SessionLocal", _fake_session_local)
    monkeypatch.setattr(
        "app.services.hub_intake_policy.hub_master_auto_approve_enabled", lambda: auto_approve
    )
    monkeypatch.setattr("app.services.storage_deposit_control.get_deposit_limit", lambda: 50)
    monkeypatch.setattr(
        "app.services.storage_deposit_control.get_deposit_media_types", lambda: "videos"
    )
    monkeypatch.setattr("app.services.storage_hub_op_status.edit_hub_op_status", lambda **kw: True)


def _held_lock_redis(token: str = "tok"):
    return MagicMock(get=lambda k: token, delete=lambda k: None)


def _run(**kwargs):
    defaults = dict(
        lane_key="ai",
        token="tok",
        chat_id=1,
        message_thread_id=2,
        status_message_id=None,
    )
    defaults.update(kwargs)
    return asyncio.run(drain.run_lane_drain(**defaults))


def test_drain_stops_when_stored_and_skipped_both_zero(monkeypatch):
    _patch_common(monkeypatch)
    monkeypatch.setattr(drain, "_redis", lambda: _held_lock_redis())

    calls = {"n": 0}

    def fake_deposit(db, **kwargs):
        calls["n"] += 1
        return {"ok": True, "job_id": f"job{calls['n']}"}

    results = [
        {"status": "done", "result": {"stored": 10, "skipped_duplicate": 0}},
        {"status": "done", "result": {"stored": 3, "skipped_duplicate": 2}},
        {"status": "done", "result": {"stored": 0, "skipped_duplicate": 0}},
    ]

    async def fake_await_job(job_id, **kwargs):
        idx = int(str(job_id).replace("job", "")) - 1
        return results[idx]

    monkeypatch.setattr(
        "app.services.storage_topic_deposit.queue_storage_topic_deposit", fake_deposit
    )
    monkeypatch.setattr(
        "app.services.storage_lane_drain._run_import_job_inline", fake_await_job
    )

    out = _run()
    assert out["stop_reason"] == "drained"
    assert out["iterations"] == 3
    assert out["total_stored"] == 13
    assert out["total_skipped_duplicate"] == 2


def test_drain_continues_past_stored_zero_when_skipped_positive(monkeypatch):
    """The exact Cursor lock: stored==0 alone must NOT stop the loop."""
    _patch_common(monkeypatch)
    monkeypatch.setattr(drain, "_redis", lambda: _held_lock_redis())

    calls = {"n": 0}

    def fake_deposit(db, **kwargs):
        calls["n"] += 1
        return {"ok": True, "job_id": f"job{calls['n']}"}

    results = [
        {"status": "done", "result": {"stored": 0, "skipped_duplicate": 5}},
        {"status": "done", "result": {"stored": 2, "skipped_duplicate": 0}},
        {"status": "done", "result": {"stored": 0, "skipped_duplicate": 0}},
    ]

    async def fake_await_job(job_id, **kwargs):
        idx = int(str(job_id).replace("job", "")) - 1
        return results[idx]

    monkeypatch.setattr(
        "app.services.storage_topic_deposit.queue_storage_topic_deposit", fake_deposit
    )
    monkeypatch.setattr(
        "app.services.storage_lane_drain._run_import_job_inline", fake_await_job
    )

    out = _run()
    assert out["iterations"] == 3
    assert out["stop_reason"] == "drained"
    assert out["total_stored"] == 2
    assert out["total_skipped_duplicate"] == 5


def test_drain_stops_on_safety_cap_iterations(monkeypatch):
    _patch_common(monkeypatch)
    monkeypatch.setenv("TBCC_LANE_DRAIN_MAX_ITERATIONS", "2")
    monkeypatch.setattr(drain, "_redis", lambda: _held_lock_redis())

    def fake_deposit(db, **kwargs):
        return {"ok": True, "job_id": "job"}

    async def fake_await_job(job_id, **kwargs):
        return {"status": "done", "result": {"stored": 5, "skipped_duplicate": 0}}

    monkeypatch.setattr(
        "app.services.storage_topic_deposit.queue_storage_topic_deposit", fake_deposit
    )
    monkeypatch.setattr(
        "app.services.storage_lane_drain._run_import_job_inline", fake_await_job
    )

    out = _run()
    assert out["stop_reason"] == "safety_cap_iterations"
    assert out["iterations"] == 2


def test_drain_stops_on_cancel(monkeypatch):
    """Clearing the lock (different token seen) must stop before the next batch starts."""
    _patch_common(monkeypatch)
    monkeypatch.setattr(drain, "_redis", lambda: _held_lock_redis(token="someone-else"))

    def fake_deposit(db, **kwargs):
        return {"ok": True, "job_id": "job"}

    async def fake_await_job(job_id, **kwargs):
        return {"status": "done", "result": {"stored": 5, "skipped_duplicate": 0}}

    monkeypatch.setattr(
        "app.services.storage_topic_deposit.queue_storage_topic_deposit", fake_deposit
    )
    monkeypatch.setattr(
        "app.services.storage_lane_drain._run_import_job_inline", fake_await_job
    )

    out = _run()
    assert out["stop_reason"] == "cancelled"
    assert out["iterations"] == 0


def test_drain_stops_on_deposit_error(monkeypatch):
    _patch_common(monkeypatch)
    monkeypatch.setattr(drain, "_redis", lambda: _held_lock_redis())

    def fake_deposit(db, **kwargs):
        return {"ok": False, "error": "unmapped_topic"}

    monkeypatch.setattr(
        "app.services.storage_topic_deposit.queue_storage_topic_deposit", fake_deposit
    )

    out = _run()
    assert out["stop_reason"] == "error:unmapped_topic"
    assert out["iterations"] == 1


def test_drain_reads_auto_approve_fresh_each_batch(monkeypatch):
    """Toggling auto-approve mid-drain must affect the next batch, not be snapshotted."""
    _patch_common(monkeypatch)
    monkeypatch.setattr(drain, "_redis", lambda: _held_lock_redis())

    approve_states = [True, False]
    seen_qa_review_only: list[bool] = []

    def fake_auto_approve():
        return approve_states.pop(0) if approve_states else False

    monkeypatch.setattr(
        "app.services.hub_intake_policy.hub_master_auto_approve_enabled", fake_auto_approve
    )

    calls = {"n": 0}

    def fake_deposit(db, **kwargs):
        calls["n"] += 1
        seen_qa_review_only.append(kwargs["qa_review_only"])
        return {"ok": True, "job_id": f"job{calls['n']}"}

    results = [
        {"status": "done", "result": {"stored": 1, "skipped_duplicate": 0}},
        {"status": "done", "result": {"stored": 0, "skipped_duplicate": 0}},
    ]

    async def fake_await_job(job_id, **kwargs):
        idx = int(str(job_id).replace("job", "")) - 1
        return results[idx]

    monkeypatch.setattr(
        "app.services.storage_topic_deposit.queue_storage_topic_deposit", fake_deposit
    )
    monkeypatch.setattr(
        "app.services.storage_lane_drain._run_import_job_inline", fake_await_job
    )

    _run()
    # First batch: auto_approve True -> qa_review_only False. Second: auto_approve False -> True.
    assert seen_qa_review_only == [False, True]


def test_drain_always_passes_sent_cache_false(monkeypatch):
    _patch_common(monkeypatch)
    monkeypatch.setattr(drain, "_redis", lambda: _held_lock_redis())

    seen = {}

    def fake_deposit(db, **kwargs):
        seen.update(kwargs)
        return {"ok": True, "job_id": "job1"}

    async def fake_await_job(job_id, **kwargs):
        return {"status": "done", "result": {"stored": 0, "skipped_duplicate": 0}}

    monkeypatch.setattr(
        "app.services.storage_topic_deposit.queue_storage_topic_deposit", fake_deposit
    )
    monkeypatch.setattr(
        "app.services.storage_lane_drain._run_import_job_inline", fake_await_job
    )

    _run()
    assert seen["sent_cache"] is False
    assert seen["auto_pipe"] is False


def test_cancel_lane_drain_clears_lock(monkeypatch):
    store = {"tbcc:storage:drain:lock:ai": "tok"}

    class _Redis:
        def get(self, k):
            return store.get(k)

        def delete(self, k):
            store.pop(k, None)

    monkeypatch.setattr(drain, "_redis", lambda: _Redis())
    assert drain.cancel_lane_drain("ai") is True
    assert "tbcc:storage:drain:lock:ai" not in store
    assert drain.cancel_lane_drain("ai") is False


def test_is_lane_draining_reflects_lock(monkeypatch):
    store: dict[str, str] = {}

    class _Redis:
        def get(self, k):
            return store.get(k)

    monkeypatch.setattr(drain, "_redis", lambda: _Redis())
    assert drain.is_lane_draining("ai") is False
    store["tbcc:storage:drain:lock:ai"] = "tok"
    assert drain.is_lane_draining("ai") is True
