"""Unit tests for clip_slug_lane_map — Phase 1 CLIP/caption -> AOF lane mapper.

Pure text/slug inputs only — no real images, no Telegram, no CLIP sidecar.
"""

from __future__ import annotations

from app.data.clip_slug_lane_map import (
    caption_confidence,
    map_clip_slugs_to_lanes,
    map_text_to_lanes,
)
from app.data.media_gatekeeper_spec import MediaGatekeeperInput, evaluate_media, glob_lane_fit


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


def test_short_fragment_keys_do_not_false_positive_on_english_words():
    # "ai" / "abg" are short LANE_TAG_MAP fragments that are also plain
    # English substrings ("waiting", "again") — must not score/propose.
    assert caption_confidence("still waiting on the rain") == 0.0
    assert map_text_to_lanes("waiting for the drop") == []
    assert map_text_to_lanes("i think this is great") == []


def test_caption_fragment_match_gets_medium_confidence():
    # "curvy" is a LANE_TAG_MAP fragment key (exact token match -> 1.0),
    # but a substring hit like "curvyness" should only score 0.55.
    assert caption_confidence("curvyness on display") == 0.55


def test_non_split_lane_tags_score_zero_confidence():
    # #amateur / #packs / #cosplay resolve in LANE_TAG_MAP but have no AOF
    # split lane — a max-confidence hit with zero proposed lanes would be a
    # silent-misroute hazard once Phase 2 wires caption_confidence into
    # auto-route (a 1.0 hit is auto-route-eligible per locked rule E).
    for caption in ("#amateur", "#homemade drop", "#packs", "#cosplay"):
        assert caption_confidence(caption) == 0.0
        assert map_text_to_lanes(caption) == []


def test_caption_confidence_and_map_text_to_lanes_agree():
    # Invariant Phase 2 will lean on: a positive confidence implies at least
    # one proposed lane, and vice versa.
    samples = [
        "horny milf drop #milf",
        "#amateur",
        "hello world nothing here",
        "curvyness on display",
        "fresh drop #ass",
        "#packs",
        "still waiting on the rain",
    ]
    for caption in samples:
        confident = caption_confidence(caption) > 0.0
        proposed = bool(map_text_to_lanes(caption))
        assert confident == proposed, caption


def test_inbox_expected_with_ass_hashtag_still_quarantines_but_proposes_ass():
    # Inbox is not a magic pass-through for tagged media — Phase 1 must not
    # let a mixed-bulk item skip straight to approve. lane_fit still flags
    # the mismatch (verdict stays quarantine); proposed_lanes carries the
    # split signal for the Phase 2 auto-split helper to consume.
    inp = MediaGatekeeperInput(
        media_type="photo",
        caption="fresh drop #ass",
        expected_lane="inbox",
    )
    result = glob_lane_fit(inp)
    assert result.pass_ is False
    assert "lane_mismatch" in result.flags
    assert "ass" in result.extra["proposed_lanes"]


def test_caption_and_clip_disagree_flags_ambiguous():
    inp = MediaGatekeeperInput(
        media_type="photo",
        caption="#milf",
        expected_lane="inbox",
        clip_slug="thick-booty",
    )
    result = glob_lane_fit(inp)
    assert result.pass_ is False
    assert "milf" in result.extra["proposed_lanes"]
    assert "ass" in result.extra["proposed_lanes"]
    assert "lane_ambiguous" in result.flags


def test_no_expected_lane_still_proposes_from_caption():
    inp = MediaGatekeeperInput(media_type="photo", caption="#blowjob content")
    result = glob_lane_fit(inp)
    assert result.pass_ is True
    assert "blowjob" in result.extra["proposed_lanes"]


def test_trusted_tagged_inbox_media_does_not_auto_approve_in_phase1():
    # No Phase 2 auto-split logic exists yet — a trusted-source hub inbox
    # deposit with a caption tag must stay quarantine (not silently jump to
    # approve just because Phase 1 added lane proposals).
    for caption in ("fresh drop #ass", ""):
        v = evaluate_media(
            MediaGatekeeperInput(
                media_type="photo",
                caption=caption,
                expected_lane="inbox",
                source_trusted=True,
                width=1080,
                height=1350,
            )
        )
        assert v.verdict != "reject"
    tagged = evaluate_media(
        MediaGatekeeperInput(
            media_type="photo",
            caption="fresh drop #ass",
            expected_lane="inbox",
            source_trusted=True,
            width=1080,
            height=1350,
        )
    )
    assert tagged.verdict == "quarantine"
    assert "ass" in tagged.globs["lane_fit"]["proposed_lanes"]


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
