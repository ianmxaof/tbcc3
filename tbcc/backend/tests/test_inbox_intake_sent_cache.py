"""Inbox intake must not vault to SENT CACHE before vision classify."""

from types import SimpleNamespace

from app.services.inbox_intake_review import _review_dest_for_media
from app.services.storage_topic_deposit import resolve_deposit_sent_cache


def test_inbox_deposit_disables_sent_cache(monkeypatch):
    monkeypatch.setenv("TBCC_STORAGE_SENT_CACHE_ENABLED", "1")
    assert resolve_deposit_sent_cache(network_key="inbox", sent_cache=None, auto_pipe=False) is False


def test_lane_deposit_keeps_sent_cache_when_enabled(monkeypatch):
    monkeypatch.setenv("TBCC_STORAGE_SENT_CACHE_ENABLED", "1")
    assert resolve_deposit_sent_cache(network_key="milf", sent_cache=None, auto_pipe=False) is True


def test_inbox_quarantine_dest_omits_general_thread_id():
    """Q&A is forum topic 1; Bot API cannot send message_thread_id=1."""
    media = SimpleNamespace(source_channel="telegram:-1003812457581#topic:22569")
    dest = _review_dest_for_media(media)
    assert dest["chat_id"] == -1003812457581
    assert dest["message_thread_id"] is None
