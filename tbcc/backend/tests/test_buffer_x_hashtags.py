"""X hashtag suffix rules for Buffer captions."""

from __future__ import annotations

from app.services.buffer_x_hashtags import (
    append_x_hashtags,
    build_x_hashtag_suffix,
    text_has_erome_link,
)


def test_erome_tag_only_with_url():
    with_url = "preview https://www.erome.com/a/abc"
    without = "full stack on Telegram hub"
    assert "#erome" in build_x_hashtag_suffix(with_url)
    assert "#erome" not in build_x_hashtag_suffix(without)


def test_lane_slug_from_text():
    tags = build_x_hashtag_suffix("New drop on AOF BIG TITS — telegram")
    assert "#bigtits" in tags
    assert "#erome" not in tags


def test_append_respects_max_chars():
    long_body = "x" * 270
    out = append_x_hashtags(long_body, max_chars=280)
    assert len(out) <= 280
    assert "#nsfw" in out
