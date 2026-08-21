"""Lightweight AOF lane tag map + scrape hashtag → pool suggestions."""

from app.services.aof_lane_tag_map import (
    build_aof_filename,
    is_aof_branded_filename,
    lane_emoji_stamp,
    lane_folder_name,
    resolve_lane_key,
    suggest_lane_keys_from_tags,
)
from app.services.scrape_channel_intel import compute_views_sample, public_telegram_url
from app.services.scrape_tag_pool_map import suggest_pool_keys_csv, suggest_pool_keys_from_hashtags


def test_suggest_abg_tags():
    keys = suggest_pool_keys_from_hashtags("#malaysian #thai #asian")
    assert "abg" in keys


def test_suggest_curvy_dual():
    keys = suggest_pool_keys_from_hashtags("#curvy")
    assert "ass" in keys
    assert "big_tits" in keys
    assert "bigtits" not in keys


def test_suggest_bbw_to_big_tits():
    assert resolve_lane_key(["bbw"]) == "big_tits"
    assert resolve_lane_key("#thick #random") == "ass"  # thick → ass first
    keys = suggest_lane_keys_from_tags("#bbw")
    assert keys == ["big_tits"]


def test_suggest_csv():
    assert suggest_pool_keys_csv("#boobs") == "big_tits"
    assert suggest_pool_keys_csv("") is None


def test_lane_folder_emoji_stamp():
    from app.services.aof_lane_tag_map import lane_folder_name

    assert lane_folder_name("big_tits", style="emoji") == "🍒 AOF BIG TITS"
    assert lane_folder_name("ass", style="emoji") == "🍑 AOF ASS"
    assert lane_folder_name(None, style="emoji") == "Unsorted"


def test_lane_folder_disk_operator_tree():
    from app.services.aof_lane_tag_map import lane_disk_folder_name, lane_folder_name

    assert lane_folder_name("milf", style="disk") == "AOF MILFGILF"
    assert lane_disk_folder_name("voyeur") == "AOF VOYPUB"
    assert lane_disk_folder_name("abg") == "AOF ABGLBFM"
    assert lane_disk_folder_name("big_tits") == "AOF BIG TITS"
    assert lane_folder_name(None, style="disk") == "Unsorted"

def test_aof_filename_branding():
    name = build_aof_filename(name="model", index=3, ext="png")
    assert name == "AOF_model_00003_telegram.me_aofmainhub.png"
    assert is_aof_branded_filename(name)
    assert not is_aof_branded_filename("photo.jpg")


def test_compute_views_sample():
    stats = compute_views_sample([100, 200, 300])
    assert stats["views_sampled"] == 3
    assert stats["avg_views_sample"] == 200.0
    assert stats["max_views_sample"] == 300
    empty = compute_views_sample([])
    assert empty["views_sampled"] == 0


def test_taboo_corpus_aliases_merged_into_lane_tag_map():
    """tag_corpus.json's taboo subtree must flow into LANE_TAG_MAP (additive
    merge in aof_lane_tag_map.py) so caption/hashtag-fragment matching picks
    up the expanded roleplay vocabulary, not just the bare 'taboo' token."""
    from app.services.aof_lane_tag_map import LANE_TAG_MAP

    assert LANE_TAG_MAP.get("stepmom") == ("taboo",)
    assert LANE_TAG_MAP.get("cheating wife") == ("taboo",)
    keys = suggest_lane_keys_from_tags("stepsis")
    assert keys == ["taboo"]


def test_public_telegram_url():
    assert public_telegram_url(username="foo") == "https://t.me/foo"
    assert public_telegram_url(identifier="@bar") == "https://t.me/bar"
    assert public_telegram_url(invite_link="https://t.me/+abc") == "https://t.me/+abc"
    assert public_telegram_url(identifier="-100123") is None
