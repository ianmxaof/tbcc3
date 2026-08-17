"""Unit tests for clip_slug_lane_map — Phase 1 CLIP/caption -> AOF lane mapper.

Pure text/slug inputs only — no real images, no Telegram, no CLIP sidecar.
"""

from __future__ import annotations

from app.data.clip_slug_lane_map import (
    caption_confidence,
    map_clip_slugs_to_lanes,
    map_text_to_lanes,
)
from app.data.media_gatekeeper_spec import MediaGatekeeperInput, glob_lane_fit


def test_blowjobs_slug_maps_to_blowjob_lane():
    ranked = map_clip_slugs_to_lanes(["blowjobs"])
    assert ranked
    assert ranked[0][0] == "blowjob"


def test_just_boobs_slug_maps_to_big_tits_lane():
    ranked = map_clip_slugs_to_lanes(["just-boobs"])
    assert ranked
    assert ranked[0][0] == "big_tits"


def test_thick_booty_slug_maps_to_ass_lane():
    ranked = map_clip_slugs_to_lanes(["thick-booty"])
    assert ranked
    assert ranked[0][0] == "ass"


def test_unmapped_slug_falls_back_to_lane_tag_map_fragment():
    # "bbc-blowjob" isn't a direct CLIP_SLUG_TO_LANE key but contains "blowjob"
    ranked = map_clip_slugs_to_lanes(["bbc-blowjob"])
    assert ranked
    assert ranked[0][0] == "blowjob"


def test_slug_score_weighting_respected():
    ranked = map_clip_slugs_to_lanes(
        ["blowjobs", "just-boobs"], scores={"blowjobs": 0.3, "just-boobs": 0.9}
    )
    assert ranked[0][0] == "big_tits"


def test_milf_caption_maps_to_milf_lane_with_full_confidence():
    lanes = map_text_to_lanes("horny milf drop #milf")
    assert lanes
    assert lanes[0] == "milf"
    assert caption_confidence("horny milf drop #milf") == 1.0


def test_untagged_caption_zero_confidence():
    assert caption_confidence("hello world nothing here") == 0.0
    assert map_text_to_lanes("hello world nothing here") == []


def test_caption_fragment_match_gets_medium_confidence():
    # "curvy" is a LANE_TAG_MAP fragment key (exact token match -> 1.0),
    # but a substring hit like "curvyness" should only score 0.55.
    assert caption_confidence("curvyness on display") == 0.55


def test_inbox_expected_with_ass_hashtag_proposes_ass_without_failing_lane_fit():
    inp = MediaGatekeeperInput(
        media_type="photo",
        caption="fresh drop #ass",
        expected_lane="inbox",
    )
    result = glob_lane_fit(inp)
    assert result.pass_ is True
    assert "ass" in result.extra["proposed_lanes"]


def test_caption_and_clip_disagree_flags_ambiguous_but_still_passes():
    inp = MediaGatekeeperInput(
        media_type="photo",
        caption="#milf",
        expected_lane="inbox",
        clip_slug="thick-booty",
    )
    result = glob_lane_fit(inp)
    assert result.pass_ is True
    assert "milf" in result.extra["proposed_lanes"]
    assert "ass" in result.extra["proposed_lanes"]
    assert "lane_ambiguous" in result.flags


def test_no_expected_lane_still_proposes_from_caption():
    inp = MediaGatekeeperInput(media_type="photo", caption="#blowjob content")
    result = glob_lane_fit(inp)
    assert result.pass_ is True
    assert "blowjob" in result.extra["proposed_lanes"]


def test_content_lane_mismatch_still_quarantines_via_pass_false():
    inp = MediaGatekeeperInput(
        media_type="video",
        caption="big ass pawg thick booty",
        duration_seconds=15.0,
        expected_lane="milf",
    )
    result = glob_lane_fit(inp)
    assert result.pass_ is False
    assert "lane_mismatch" in result.flags
    assert "ass" in result.extra["proposed_lanes"]
