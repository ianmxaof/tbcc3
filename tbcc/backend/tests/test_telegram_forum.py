"""Bot API forum thread id quirks (General / Q&A topic 1)."""

from __future__ import annotations

from app.utils.telegram_forum import (
    bot_api_forum_thread_id,
    bot_api_incoming_forum_thread_id,
)


def test_bot_api_outgoing_omits_general_topic():
    assert bot_api_forum_thread_id(None) is None
    assert bot_api_forum_thread_id(1) is None
    assert bot_api_forum_thread_id(0) is None
    assert bot_api_forum_thread_id(5978) == 5978


def test_bot_api_incoming_treats_missing_as_general():
    assert bot_api_incoming_forum_thread_id(None) == 1
    assert bot_api_incoming_forum_thread_id(1) == 1
    assert bot_api_incoming_forum_thread_id(5978) == 5978


def test_qa_master_forum_context_accepts_missing_thread(monkeypatch):
    """Master panel callbacks in Q&A (topic 1) arrive without message_thread_id."""
    from bots.qa_master_panel_handlers import _forum_context_from_message

    monkeypatch.setattr(
        "bots.qa_master_panel_handlers.storage_hub_chat_id_int",
        lambda: -1003812457581,
    )

    class _Chat:
        id = -1003812457581

    class _Msg:
        chat = _Chat()
        message_thread_id = None

    ok, tid = _forum_context_from_message(_Msg())
    assert ok is True
    assert tid == 1


def test_is_qa_intake_thread_none_when_qa_is_general():
    from app.services.hub_panel_activity import is_qa_intake_thread

    assert is_qa_intake_thread(None) is True
    assert is_qa_intake_thread(1) is True
    assert is_qa_intake_thread(5978) is False
