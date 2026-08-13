"""Storage Hub album intake + deposit control presets."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.storage_deposit_control import (
    MEDIA_TYPES,
    adjust_deposit_limit,
    cycle_deposit_media_types,
    deposit_control_keyboard,
    format_deposit_command,
    get_deposit_limit,
    get_deposit_media_types,
    media_type_label,
    set_deposit_limit,
)
from app.services.storage_hub_album_intake import (
    dest_key_for_topic,
    resolve_dest_key,
    storage_hub_album_intake_enabled,
)


def test_dest_key_for_topic():
    assert dest_key_for_topic(9505) == "topic:9505"


def test_resolve_dest_key_inbox_channel():
    from app.data.aof_storage_hub_map import INBOX_CHANNEL_IDENT

    assert resolve_dest_key(channel_ident=INBOX_CHANNEL_IDENT) == f"channel:{INBOX_CHANNEL_IDENT.lstrip('-')}"


def test_snap_limit_steps_of_fifty():
    from app.services.storage_deposit_control import _snap_limit

    assert _snap_limit(50) == 50
    assert _snap_limit(175) == 150
    assert _snap_limit(200) == 200


def test_adjust_deposit_limit_from_redis():
    fake = MagicMock()
    fake.get.return_value = "50"
    fake.set = MagicMock()
    with patch("app.services.storage_deposit_control._redis", return_value=fake):
        assert adjust_deposit_limit(1) == 100
        assert adjust_deposit_limit(-1) == 50


def test_deposit_media_cycle(monkeypatch):
    fake = MagicMock()
    fake.get.return_value = "videos"
    fake.set = MagicMock()
    with patch("app.services.storage_deposit_control._redis", return_value=fake):
        assert cycle_deposit_media_types(1) == "photos"
        fake.get.return_value = "photos"
        assert cycle_deposit_media_types(1) == "both"
        fake.get.return_value = "both"
        assert cycle_deposit_media_types(1) == "videos"


def test_media_type_label_maps_photos_to_image():
    assert media_type_label("photos") == "image"
    assert media_type_label("videos") == "video"
    assert media_type_label("both") == "both"


def test_format_deposit_command():
    assert format_deposit_command(100, "both") == "/deposit 100 both"
    assert format_deposit_command(50, "photos") == "/deposit 50 image"


def test_deposit_control_keyboard_has_presets():
    kb = deposit_control_keyboard()
    rows = kb.get("inline_keyboard") or []
    assert len(rows) >= 4
    preset_row = rows[3]
    labels = [b["text"] for b in preset_row]
    assert "50" in labels[0]
    assert "100" in labels[1]
    assert "150" in labels[2]


def test_album_intake_enabled_by_default():
    assert storage_hub_album_intake_enabled() is True


def test_enqueue_buffers_without_flush_when_below_album_size(monkeypatch, tmp_path):
    from app.services import storage_hub_album_intake as mod

    monkeypatch.setattr(mod, "BUFFER_ROOT", tmp_path / "buf")
    monkeypatch.setattr(mod, "get_album_size", lambda: 5)
    monkeypatch.setattr(mod, "flush_storage_hub_album_buffer", lambda *a, **k: [])
    monkeypatch.setattr(mod, "pending_count", lambda _k: 1)

    fake = MagicMock()
    fake.rpush = MagicMock()
    fake.expire = MagicMock()
    with patch.object(mod, "_redis", return_value=fake):
        out = mod.enqueue_storage_hub_media(
            raw=b"\xff\xd8\xff",
            media_type="photo",
            message_thread_id=9505,
        )
    assert out.get("buffered") is True
    assert out.get("pending") == 1
    fake.rpush.assert_called_once()
