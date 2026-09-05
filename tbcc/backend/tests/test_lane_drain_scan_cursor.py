"""The drain carries a scan cursor, so batches advance instead of re-reading the head.

2026-09-04, before the cursor: a taboo drain ended on `safety_cap_iterations` with 0 stored
and 7360 duplicates. 40 iterations x 184 messages = 7360 — every batch re-scanned the same
newest messages. With no cursor the stop condition (a fully empty batch) is unreachable once
the head is indexed, so the loop burns its whole iteration cap doing identical work.
"""

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from app.services import storage_lane_drain as drain


class _FakeRedis:
    def __init__(self):
        self.store = {}
        self.ttls = {}

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

    def ttl(self, k):
        return self.ttls.get(k, -1)


@pytest.fixture
def fake_redis(monkeypatch):
    r = _FakeRedis()
    monkeypatch.setattr(drain, "_redis", lambda: r)
    r.set(drain._lock_key("taboo"), drain._lock_payload("tok", "queued"), ex=2100)
    return r


def _drive(job_results):
    """Run the drain over scripted import results; return (summary, deposit kwargs list)."""
    deposits = []

    def _queue_deposit(db, **kw):
        deposits.append(kw)
        return {"ok": True, "job_id": f"job{len(deposits)}"}

    results = list(job_results)

    async def _inline(job_id):
        return results.pop(0) if results else {"status": "done", "messages_scanned": 0}

    with patch.object(drain, "_run_import_job_inline", side_effect=_inline), patch(
        "app.services.storage_topic_deposit.queue_storage_topic_deposit",
        side_effect=_queue_deposit,
    ), patch("app.database.session.SessionLocal", MagicMock()), patch(
        "app.services.hub_intake_policy.hub_master_auto_approve_enabled", return_value=True
    ), patch(
        "app.services.storage_deposit_control.get_deposit_limit", return_value=184
    ), patch(
        "app.services.storage_deposit_control.get_deposit_media_types", return_value="both"
    ), patch(
        "app.services.storage_hub_op_status.edit_hub_op_status", MagicMock()
    ):
        out = asyncio.run(
            drain.run_lane_drain(
                "taboo", token="tok", chat_id=-100, message_thread_id=2919, status_message_id=None
            )
        )
    return out, deposits


def test_first_batch_starts_at_the_head(fake_redis):
    _out, deposits = _drive([{"status": "done", "messages_scanned": 0}])

    assert deposits[0]["offset_id"] is None


def test_each_batch_resumes_below_the_previous_one(fake_redis):
    _out, deposits = _drive(
        [
            {"status": "done", "stored": 5, "skipped_duplicate": 0,
             "messages_scanned": 10, "oldest_scanned_message_id": 900},
            {"status": "done", "stored": 2, "skipped_duplicate": 3,
             "messages_scanned": 10, "oldest_scanned_message_id": 850},
            {"status": "done", "messages_scanned": 0},
        ]
    )

    assert [d["offset_id"] for d in deposits] == [None, 900, 850]


def test_all_duplicates_does_not_stop_the_drain(fake_redis):
    """A fully-indexed stretch is not the end of the topic — older uniques may follow.

    This is the operator's explicit instruction: do not treat all-duplicates as drained.
    """
    out, deposits = _drive(
        [
            {"status": "done", "stored": 0, "skipped_duplicate": 184,
             "messages_scanned": 184, "oldest_scanned_message_id": 900},
            {"status": "done", "stored": 0, "skipped_duplicate": 184,
             "messages_scanned": 184, "oldest_scanned_message_id": 700},
            # Older unique content sitting behind the indexed head — would have been
            # abandoned by an all-duplicates stop.
            {"status": "done", "stored": 9, "skipped_duplicate": 0,
             "messages_scanned": 9, "oldest_scanned_message_id": 500},
            {"status": "done", "messages_scanned": 0},
        ]
    )

    assert out["total_stored"] == 9
    assert out["stop_reason"] == "drained"
    assert len(deposits) == 4


def test_drained_means_the_topic_is_exhausted(fake_redis):
    out, _ = _drive(
        [
            {"status": "done", "stored": 3, "skipped_duplicate": 1,
             "messages_scanned": 4, "oldest_scanned_message_id": 900},
            {"status": "done", "messages_scanned": 0},
        ]
    )

    assert out["stop_reason"] == "drained"
    assert out["total_scanned"] == 4
    assert out["last_cursor_message_id"] == 900


def test_the_7360_regression_cannot_repeat(fake_redis, monkeypatch):
    """Re-scanning the same head 40 times must no longer be possible.

    Model the pre-fix island run: every batch reports the same 184 already-indexed
    messages. With a cursor the offsets strictly decrease, so the drain walks the topic
    instead of looping on the head.
    """
    monkeypatch.setenv("TBCC_LANE_DRAIN_MAX_ITERATIONS", "40")

    oldest = 10_000
    results = []
    for _ in range(6):
        oldest -= 184
        results.append(
            {"status": "done", "stored": 0, "skipped_duplicate": 184,
             "messages_scanned": 184, "oldest_scanned_message_id": oldest}
        )
    results.append({"status": "done", "messages_scanned": 0})

    out, deposits = _drive(results)

    offsets = [d["offset_id"] for d in deposits]
    assert offsets[0] is None
    advancing = [o for o in offsets if o is not None]
    assert advancing == sorted(advancing, reverse=True), "cursor must move strictly older"
    assert len(set(advancing)) == len(advancing), "no offset may repeat"
    assert out["stop_reason"] == "drained"
    assert out["total_skipped_duplicate"] == 184 * 6
