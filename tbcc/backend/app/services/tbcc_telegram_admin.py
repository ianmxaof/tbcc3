"""Who may run TBCC admin commands in Storage Hub (personal admins + post-as-group)."""

from __future__ import annotations

import os

from app.data.aof_storage_hub_map import STORAGE_HUB_IDENT
from app.services.admin_inbox import admin_telegram_ids

# Telegram «Group Anonymous Bot» — effective_user when posting anonymously as admin.
GROUP_ANONYMOUS_BOT_ID = 1087968824


def storage_hub_chat_id_int() -> int:
    return int(STORAGE_HUB_IDENT)


def storage_hub_channel_post_allowed() -> bool:
    raw = (os.getenv("TBCC_STORAGE_HUB_ALLOW_CHANNEL_POST") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def storage_hub_sender_chat_ids() -> set[int]:
    """Extra sender_chat ids allowed (comma-separated), e.g. linked channel."""
    ids: set[int] = {storage_hub_chat_id_int()}
    raw = (os.getenv("TBCC_STORAGE_HUB_SENDER_CHAT_IDS") or "").strip()
    for part in raw.split(","):
        token = part.strip()
        if not token:
            continue
        try:
            ids.add(int(token))
        except ValueError:
            continue
    return ids


def is_configured_tbcc_admin(user_id: int | None) -> bool:
    if user_id is None:
        return False
    return int(user_id) in admin_telegram_ids()


def _in_storage_hub_chat(chat_id: int | None) -> bool:
    if chat_id is None:
        return False
    return int(chat_id) == storage_hub_chat_id_int()


def can_operate_storage_hub_bot_api(update) -> bool:
    """
    Secretary / Bot API: allow configured admin user ids, or post-as-Storage-Hub
    (sender_chat / anonymous admin) inside the hangar group.
    """
    user = getattr(update, "effective_user", None)
    if is_configured_tbcc_admin(getattr(user, "id", None)):
        return True

    chat = getattr(update, "effective_chat", None)
    chat_id = int(chat.id) if chat else None
    if not _in_storage_hub_chat(chat_id):
        return False
    if not storage_hub_channel_post_allowed():
        return False

    msg = getattr(update, "effective_message", None)
    if not msg:
        return False

    sender_chat = getattr(msg, "sender_chat", None)
    if sender_chat and int(sender_chat.id) in storage_hub_sender_chat_ids():
        return True

    uid = getattr(user, "id", None)
    if uid is not None and int(uid) == GROUP_ANONYMOUS_BOT_ID:
        return True

    return False


def can_operate_storage_hub_telethon(event) -> bool:
    """Admin bot (Telethon): same policy for /deposit and /erome."""
    sender = getattr(event, "sender_id", None)
    if is_configured_tbcc_admin(sender):
        return True

    if not _is_storage_hub_chat_telethon(getattr(event, "chat_id", None)):
        return False
    if not storage_hub_channel_post_allowed():
        return False

    if sender is not None and int(sender) == GROUP_ANONYMOUS_BOT_ID:
        return True

    msg = getattr(event, "message", None)
    if msg is None:
        return False

    peer = getattr(msg, "from_id", None)
    channel_id = getattr(peer, "channel_id", None)
    if channel_id is not None:
        # Post signed as linked channel inside the supergroup.
        return True

    if bool(getattr(msg, "post", False)):
        return True

    # Some clients send the supergroup id as sender when posting as the group.
    hub = storage_hub_chat_id_int()
    if sender is not None and abs(int(sender)) == abs(hub):
        return True

    return False


def _is_storage_hub_chat_telethon(chat_id) -> bool:
    if chat_id is None:
        return False
    try:
        return int(chat_id) == storage_hub_chat_id_int()
    except (TypeError, ValueError):
        return False
