"""Pinned storage deposit panel targets."""

from app.services.storage_deposit_panel_pins import (
    panel_redis_key,
    storage_deposit_panel_targets,
)


def test_panel_redis_key_uses_thread():
    assert panel_redis_key(-1003812457581, 9505) == "tbcc:storage:deposit:panel:msg:-1003812457581:9505"
    assert panel_redis_key(-1003874330989, None) == "tbcc:storage:deposit:panel:msg:-1003874330989:0"


def test_storage_deposit_panel_targets_include_ass_and_inbox():
    from app.data.aof_storage_hub_map import INBOX_CHANNEL_ACTIVE, INBOX_CHANNEL_IDENT

    targets = storage_deposit_panel_targets()
    threads = {int(t["message_thread_id"]) for t in targets if t.get("message_thread_id")}
    assert 3779 in threads  # ASS
    assert 22569 in threads  # inbox forum topic
    channels = {int(t["chat_id"]) for t in targets if t.get("message_thread_id") is None}
    # Decommissioned standalone shortcut channel must not be pinned as a target.
    assert INBOX_CHANNEL_ACTIVE is False
    assert int(INBOX_CHANNEL_IDENT) not in channels
