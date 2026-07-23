"""Unit tests for media_gatekeeper_spec — pattern classes, score math, worked examples."""

from __future__ import annotations

import pytest

from app.data.aof_scrape_inbound_map import SKIP_INBOUND_CHAT_IDS
from app.data.media_gatekeeper_spec import (
    QUALITY_BASE_SCORE,
    SCORE_APPROVE_MIN,
    SCORE_QUARANTINE_MIN,
    MediaGatekeeperInput,
    caption_url_spam_ratio,
    clamp_score,
    evaluate_media,
    glob_hard_block,
    glob_trash,
    is_age_adjacent,
    is_seller_proof,
    is_zoo_keyword,
    merge_gatekeeper_json,
)


# ---------------------------------------------------------------------------
# Pattern helpers
# ---------------------------------------------------------------------------


def test_age_adjacent_detects_synthetic_caption():
    assert is_age_adjacent("menu for underage seller proof", "")
    assert not is_age_adjacent("milf ass big booty", "")


def test_seller_proof_detects_menu_rates():
    assert is_seller_proof("DM for rates and verification menu", "")
    assert not is_seller_proof("fresh lane drop #ass", "")


def test_zoo_keyword_rejects():
    assert is_zoo_keyword("bestiality compilation", "")
    assert not is_zoo_keyword("ass pawg thick", "")


def test_caption_url_spam_ratio():
    assert caption_url_spam_ratio("https://t.me/foo @bar https://x.com/y") >= 0.8
    assert caption_url_spam_ratio("nice ass clip #modelname") < 0.5


def test_clamp_score():
    assert clamp_score(150) == 100
    assert clamp_score(-10) == 0
    assert clamp_score(72) == 72


# ---------------------------------------------------------------------------
# Worked example 1 — seller-proof underage screenshot → quarantine
# ---------------------------------------------------------------------------


def test_example1_seller_proof_underage_quarantine():
    inp = MediaGatekeeperInput(
        media_type="photo",
        caption="underage seller social proof verification menu rates",
        filename="seller_proof.jpg",
        width=1080,
        height=1920,
        expected_lane="ass",
        source_trusted=True,
    )
    v = evaluate_media(inp)
    assert v.verdict == "quarantine"
    assert v.quality_score >= SCORE_QUARANTINE_MIN
    assert any("hard_block" in w for w in v.warnings)


# ---------------------------------------------------------------------------
# Worked example 2 — 7s vertical clip, model hashtag, ASS, explicit, trusted → approve
# ---------------------------------------------------------------------------


def test_example2_vertical_clip_trusted_approve():
    inp = MediaGatekeeperInput(
        media_type="video",
        caption="fire drop #modelname #ass #pawg",
        duration_seconds=7.0,
        width=1080,
        height=1920,
        expected_lane="ass",
        nsfw_tier="explicit",
        source_trusted=True,
        clip_slug="ass",
        clip_confident=True,
    )
    v = evaluate_media(inp)
    assert v.verdict == "approve"
    assert v.quality_score >= SCORE_APPROVE_MIN


def test_example2_untrusted_high_score_still_quarantine():
    """Score ≥70 but new source → quarantine per doctrine."""
    inp = MediaGatekeeperInput(
        media_type="video",
        caption="fire drop #modelname #ass",
        duration_seconds=7.0,
        width=1080,
        height=1920,
        expected_lane="ass",
        nsfw_tier="explicit",
        source_trusted=False,
    )
    v = evaluate_media(inp)
    assert v.verdict == "quarantine"
    assert v.quality_score >= SCORE_APPROVE_MIN


# ---------------------------------------------------------------------------
# Worked example 3 — ASS content in MILF topic → quarantine
# ---------------------------------------------------------------------------


def test_example3_lane_mismatch_quarantine():
    inp = MediaGatekeeperInput(
        media_type="video",
        caption="big ass pawg thick booty",
        duration_seconds=15.0,
        width=1080,
        height=1920,
        expected_lane="milf",
        nsfw_tier="explicit",
        source_trusted=True,
    )
    v = evaluate_media(inp)
    assert v.verdict == "quarantine"
    assert v.globs["lane_fit"]["detected"] == "ass"
    assert v.globs["lane_fit"]["expected"] == "milf"


# ---------------------------------------------------------------------------
# Worked example 4 — 2s video, URL wall → reject
# ---------------------------------------------------------------------------


def test_example4_short_video_url_spam_reject():
    inp = MediaGatekeeperInput(
        media_type="video",
        caption="https://t.me/foo @bar https://x.com/y https://z.com/w",
        duration_seconds=2.0,
        expected_lane="ass",
    )
    v = evaluate_media(inp)
    assert v.verdict == "reject"
    assert any("trash:" in b for b in v.blocks)


# ---------------------------------------------------------------------------
# Threshold edges
# ---------------------------------------------------------------------------


def test_zoo_hard_block_reject():
    inp = MediaGatekeeperInput(
        media_type="photo",
        caption="bestiality zoo content",
        expected_lane="taboo",
        source_trusted=True,
    )
    v = evaluate_media(inp)
    assert v.verdict == "reject"
    assert any("zoo" in b for b in v.blocks)


def test_known_bad_source_reject():
    bad_id = next(iter(SKIP_INBOUND_CHAT_IDS))
    inp = MediaGatekeeperInput(
        media_type="photo",
        caption="normal ass content",
        source_channel_id=bad_id,
        expected_lane="ass",
        source_trusted=True,
    )
    v = evaluate_media(inp)
    assert v.verdict == "reject"


def test_low_quality_score_reject():
    inp = MediaGatekeeperInput(
        media_type="photo",
        caption="",
        width=200,
        height=300,
        filesize_bytes=50_000,
        expected_lane="ass",
        nsfw_tier="suggestive",
        is_letterbox=True,
    )
    v = evaluate_media(inp)
    assert v.verdict == "reject"
    assert v.quality_score < SCORE_QUARANTINE_MIN


def test_duplicate_trash_reject():
    inp = MediaGatekeeperInput(
        media_type="photo",
        caption="#ass",
        is_duplicate_in_pool=True,
        expected_lane="ass",
    )
    v = evaluate_media(inp)
    assert v.verdict == "reject"
    assert "trash:duplicate" in v.blocks


def test_non_media_type_reject():
    inp = MediaGatekeeperInput(media_type="document", caption="zip pack")
    v = evaluate_media(inp)
    assert v.verdict == "reject"


def test_merge_gatekeeper_json_preserves_keys():
    merged = merge_gatekeeper_json(
        {"lustpress": {"title": "x"}},
        evaluate_media(MediaGatekeeperInput(media_type="photo", caption="#ass", expected_lane="ass")),
    )
    assert "lustpress" in merged
    assert "gatekeeper" in merged
    assert merged["gatekeeper"]["verdict"] in ("reject", "quarantine", "approve")


def test_glob_hard_block_pass_clean():
    r = glob_hard_block(MediaGatekeeperInput(caption="ass pawg #milf"))
    assert r.pass_ is True
    assert r.flags == []


def test_glob_trash_photo_too_small():
    r = glob_trash(
        MediaGatekeeperInput(
            media_type="photo",
            width=400,
            height=600,
        )
    )
    assert r.pass_ is False
    assert "photo_too_small" in r.flags


def test_quality_base_score_constant():
    inp = MediaGatekeeperInput(media_type="photo", caption="neutral")
    v = evaluate_media(inp)
    # unknown source -5 from 50 = 45 → quarantine band
    assert v.quality_score == QUALITY_BASE_SCORE - 5
