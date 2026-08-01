"""Buffer mirror channel policy."""

from app.services.buffer_mirror_policy import (
    buffer_mirror_allowed_for_telegram_identifier,
    is_banned_main_telegram_identifier,
    is_loot_room_hub_identifier,
)


def test_banned_main_blocked():
    assert is_banned_main_telegram_identifier("-1003206350461")
    assert not buffer_mirror_allowed_for_telegram_identifier("-1003206350461")


def test_loot_room_allowed():
    assert is_loot_room_hub_identifier("-1003927742839")
    assert buffer_mirror_allowed_for_telegram_identifier("-1003927742839")


def test_vip_allowed():
    assert buffer_mirror_allowed_for_telegram_identifier("-1003982098745")
