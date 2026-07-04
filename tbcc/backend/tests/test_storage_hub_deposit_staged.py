"""Staged storage hub deposit queue."""

from app.services.storage_topic_deposit import queue_storage_topic_deposit_staged


def test_queue_staged_requires_ids():
    class _Db:
        pass

    out = queue_storage_topic_deposit_staged(_Db(), message_thread_id=9505, message_ids=[])
    assert out.get("ok") is False
    assert out.get("error") == "no_message_ids"
