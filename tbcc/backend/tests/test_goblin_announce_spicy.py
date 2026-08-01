"""Goblin announce spicybot CTA."""

from app.services.goblin_announce import (
    build_goblin_deep_link,
    build_spicybot_trial_deep_link,
)


def test_goblin_deep_link():
    assert build_goblin_deep_link("tok123").endswith("?start=goblin_tok123")


def test_spicybot_trial_deep_link_with_drop():
    url = build_spicybot_trial_deep_link(drop_id=42)
    assert "aof_spicybot_bot" in url
    assert url.endswith("?start=src_spicy_goblin_42")


def test_spicybot_trial_deep_link_generic():
    url = build_spicybot_trial_deep_link()
    assert url.endswith("?start=src_spicy_goblin")
