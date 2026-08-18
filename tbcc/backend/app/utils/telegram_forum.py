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


def bot_api_incoming_forum_thread_id(thread_id: int | None) -> int:
    """
    Normalize message_thread_id from an incoming Bot API Message / callback.

    Telegram omits message_thread_id for the General topic (id 1), including when
    that topic was renamed (Storage Hub Q&A | APPROVE / DENY | INTAKE). Treat
    a missing thread id as 1 so panel callbacks in that topic do not fail the
    "open a forum subtopic first" gate.
    """
    if thread_id is None:
        return 1
    return int(thread_id)


def bot_api_forum_thread_api_kwargs(message_thread_id: int | None) -> dict[str, int]:
    """Bot API forum thread id for pin/unpin — pass as api_kwargs to PTB methods."""
    api_thread = bot_api_forum_thread_id(message_thread_id)
    if api_thread:
        return {"message_thread_id": api_thread}
    return {}
