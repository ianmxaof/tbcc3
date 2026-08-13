"""Telegram forum topic helpers for Bot API vs Telethon id quirks."""

from __future__ import annotations


def bot_api_forum_thread_id(thread_id: int | None) -> int | None:
    """
    Bot API cannot target forum thread_id=1 (General / renamed Q&A topic).

    Telethon lists that topic as id 1; send without message_thread_id instead.
    """
    if thread_id is None:
        return None
    tid = int(thread_id)
    if tid <= 1:
        return None
    return tid
