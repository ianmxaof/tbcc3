"""Forum topic id extraction from Telethon messages."""

from app.services.storage_topic_deposit import forum_message_thread_id_from_telethon


def test_forum_thread_id_from_reply_to_top_id_without_forum_flag():
    class _Reply:
        reply_to_top_id = 3090
        forum_topic = False

    class _Msg:
        reply_to_top_id = None
        reply_to = _Reply()

    assert forum_message_thread_id_from_telethon(_Msg()) == 3090


def test_forum_thread_id_on_message_direct():
    class _Msg:
        reply_to_top_id = 3090
        reply_to = None

    assert forum_message_thread_id_from_telethon(_Msg()) == 3090
