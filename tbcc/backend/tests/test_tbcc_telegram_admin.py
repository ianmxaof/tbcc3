"""Storage Hub operator auth (personal admin + post-as-group)."""

from app.data.aof_storage_hub_map import STORAGE_HUB_IDENT
from app.services.tbcc_telegram_admin import (
    GROUP_ANONYMOUS_BOT_ID,
    can_operate_storage_hub_bot_api,
)


class _User:
    def __init__(self, uid: int):
        self.id = uid


class _Chat:
    def __init__(self, cid: int):
        self.id = cid


class _SenderChat:
    def __init__(self, cid: int, title: str = ""):
        self.id = cid
        self.title = title
        self.username = None


class _Msg:
    def __init__(self, *, sender_chat=None, thread_id: int | None = 3387):
        self.sender_chat = sender_chat
        self.message_thread_id = thread_id


class _Update:
    def __init__(self, user, chat, message):
        self.effective_user = user
        self.effective_chat = chat
        self.effective_message = message


def test_personal_admin_allowed(monkeypatch):
    monkeypatch.setenv("ADMIN_TELEGRAM_ID", "7787282561")
    hub = int(STORAGE_HUB_IDENT)
    upd = _Update(_User(7787282561), _Chat(hub), _Msg(thread_id=3387))
    assert can_operate_storage_hub_bot_api(upd) is True


def test_extra_admin_allowed(monkeypatch):
    monkeypatch.setenv("ADMIN_TELEGRAM_ID", "7787282561")
    monkeypatch.setenv("TBCC_ALBUM_COMPOSER_EXTRA_ADMIN_IDS", "8630278848")
    hub = int(STORAGE_HUB_IDENT)
    upd = _Update(_User(8630278848), _Chat(hub), _Msg(thread_id=3387))
    assert can_operate_storage_hub_bot_api(upd) is True


def test_post_as_storage_hub_sender_chat(monkeypatch):
    monkeypatch.setenv("ADMIN_TELEGRAM_ID", "7787282561")
    hub = int(STORAGE_HUB_IDENT)
    upd = _Update(
        _User(GROUP_ANONYMOUS_BOT_ID),
        _Chat(hub),
        _Msg(sender_chat=_SenderChat(hub, "Storage & Bot Hangar"), thread_id=3387),
    )
    assert can_operate_storage_hub_bot_api(upd) is True


def test_random_user_denied(monkeypatch):
    monkeypatch.setenv("ADMIN_TELEGRAM_ID", "7787282561")
    hub = int(STORAGE_HUB_IDENT)
    upd = _Update(_User(999), _Chat(hub), _Msg(thread_id=3387))
    assert can_operate_storage_hub_bot_api(upd) is False
