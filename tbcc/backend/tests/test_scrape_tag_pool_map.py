"""Lightweight scrape hashtag → pool map + view sample helpers."""

from app.services.scrape_channel_intel import compute_views_sample, public_telegram_url
from app.services.scrape_tag_pool_map import suggest_pool_keys_csv, suggest_pool_keys_from_hashtags


def test_suggest_abg_tags():
    keys = suggest_pool_keys_from_hashtags("#malaysian #thai #asian")
    assert "abg" in keys


def test_suggest_curvy_dual():
    keys = suggest_pool_keys_from_hashtags("#curvy")
    assert "ass" in keys
    assert "bigtits" in keys


def test_suggest_csv():
    assert suggest_pool_keys_csv("#boobs") == "bigtits"
    assert suggest_pool_keys_csv("") is None


def test_compute_views_sample():
    stats = compute_views_sample([100, 200, 300])
    assert stats["views_sampled"] == 3
    assert stats["avg_views_sample"] == 200.0
    assert stats["max_views_sample"] == 300
    empty = compute_views_sample([])
    assert empty["views_sampled"] == 0


def test_public_telegram_url():
    assert public_telegram_url(username="foo") == "https://t.me/foo"
    assert public_telegram_url(identifier="@bar") == "https://t.me/bar"
    assert public_telegram_url(invite_link="https://t.me/+abc") == "https://t.me/+abc"
    assert public_telegram_url(identifier="-100123") is None
