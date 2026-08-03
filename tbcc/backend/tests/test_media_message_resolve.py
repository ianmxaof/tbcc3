"""Tests for media message peer resolution."""

from types import SimpleNamespace

from app.services.media_message_resolve import media_fetch_peer_label


def test_media_fetch_peer_label_hub_deposit():
    row = SimpleNamespace(
        source_channel="telegram:-1003812457581#topic:5978",
        telegram_message_id=12345,
    )
    assert media_fetch_peer_label(row) == "hub"


def test_media_fetch_peer_label_saved_messages():
    row = SimpleNamespace(
        source_channel="some-scrape-channel",
        telegram_message_id=99,
    )
    assert media_fetch_peer_label(row) == "me"
