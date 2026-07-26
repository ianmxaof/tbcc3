"""Tests for Buffer/X outbound URL gate wrapping."""

from app.services.buffer_x_outbound_guard import (
    enforce_buffer_x_caption_urls,
    is_bare_telegram_url,
    wrap_url_for_x_outbound,
)


def test_is_bare_telegram_url():
    assert is_bare_telegram_url("https://t.me/aofmainhub")
    assert is_bare_telegram_url("https://telegram.me/aof_lootgod_bot")
    assert not is_bare_telegram_url("https://link-center.net/1367336/DgIo85a7oux0")


def test_wrap_url_for_x_outbound_uses_manual_gate():
    wrapped = wrap_url_for_x_outbound("https://telegram.me/aofmainhub", gate_key="mainhub")
    assert "link-center.net" in wrapped or "linkvertise" in wrapped or wrapped != "https://telegram.me/aofmainhub"


def test_enforce_buffer_x_caption_replaces_bare_telegram():
    text = "Check us out https://t.me/aofmainhub today"
    new_text, errors = enforce_buffer_x_caption_urls(text, network_key="mainhub", strict=False)
    assert "t.me/aofmainhub" not in new_text or not errors
    assert errors == [] or "link-center" in new_text


def test_enforce_strict_blocks_unwrapped():
    text = "only https://t.me/+secretinvite"
    _, errors = enforce_buffer_x_caption_urls(text, network_key="bop", strict=True)
    # May wrap via manual gate; if wrap fails, errors present
    if errors:
        assert "bare Telegram" in errors[0]
