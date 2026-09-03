"""Quarantine review Telegram cleanup + panel thread normalization."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest


def test_normalize_hub_panel_thread_id_maps_general_topic():
    from app.utils.telegram_forum import normalize_hub_panel_thread_id

    assert normalize_hub_panel_thread_id(None) == 1
    assert normalize_hub_panel_thread_id(0) == 1
    assert normalize_hub_panel_thread_id(1) == 1
    assert normalize_hub_panel_thread_id(22569) == 22569


def test_cleanup_media_quarantine_messages_deletes_and_clears_json(monkeypatch):
    from app.services.quarantine_review_cleanup import cleanup_media_quarantine_messages

    media = MagicMock()
    media.id = 42
    media.classification_json = json.dumps(
        {
            "gatekeeper": {
                "quarantine_review_chat_id": -1003812457581,
                "quarantine_review_message_ids": [9001, 9002],
            }
        }
    )

    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = media

    deleted: list[int] = []

    def _fake_delete(chat_id, message_ids):
        deleted.extend(message_ids)
        return {"ok": True, "deleted": len(message_ids)}

    monkeypatch.setattr(
        "app.services.quarantine_review_cleanup._delete_messages_http",
        _fake_delete,
    )

    out = cleanup_media_quarantine_messages(db, 42)
    assert out["deleted"] == 2
    assert sorted(deleted) == [9001, 9002]
    cleared_raw = media.classification_json
    if cleared_raw:
        cleared = json.loads(cleared_raw)
        assert "quarantine_review_message_ids" not in (cleared.get("gatekeeper") or {})
    else:
        assert cleared_raw is None


def test_cleanup_batch_quarantine_messages(monkeypatch):
    from app.services.quarantine_review_cleanup import cleanup_batch_quarantine_messages

    monkeypatch.setattr(
        "app.services.quarantine_batch_review.load_batch_payload",
        lambda _bid: {
            "media_ids": [1, 2],
            "telegram": {
                "chat_id": -1003812457581,
                "preview_message_ids": [100, 101],
                "control_message_id": 200,
            },
        },
    )
    saved: dict = {}

    def _save(batch_id, **kwargs):
        saved.update(kwargs)

    monkeypatch.setattr(
        "app.services.quarantine_batch_review.save_batch_telegram_meta",
        _save,
    )
    deleted: list[int] = []
    monkeypatch.setattr(
        "app.services.quarantine_review_cleanup._delete_messages_http",
        lambda chat_id, ids: deleted.extend(ids) or {"ok": True, "deleted": len(ids)},
    )

    out = cleanup_batch_quarantine_messages("abcd")
    assert out["deleted"] == 3
    assert sorted(deleted) == [100, 101, 200]
    assert saved.get("preview_message_ids") == []
    assert saved.get("control_message_id") == 0


def test_force_new_deletes_stored_panel_before_repost():
    import asyncio

    from app.services.hub_panel_message import ensure_singleton_panel_message

    deleted: list[int] = []
    sent = MagicMock()
    sent.message_id = 99

    class _Bot:
        async def edit_message_text(self, **kwargs):
            raise RuntimeError("should not edit when force_new")

        async def send_message(self, **kwargs):
            return sent

    async def _delete(bot, **kwargs):
        deleted.append(int(kwargs["message_id"]))

    stored = {"mid": 55}

    with patch("app.services.hub_panel_message.delete_panel_message", _delete):
        out = asyncio.run(
            ensure_singleton_panel_message(
                _Bot(),
                chat_id=-100,
                message_thread_id=1,
                text="hello",
                parse_mode="HTML",
                reply_markup=None,
                force_new=True,
                get_stored_message_id=lambda: stored["mid"],
                set_stored_message_id=lambda mid: stored.update(mid=mid),
                panel_label="test",
            )
        )

    assert deleted == [55]
    assert out["action"] == "posted"
    assert out["message_id"] == 99
