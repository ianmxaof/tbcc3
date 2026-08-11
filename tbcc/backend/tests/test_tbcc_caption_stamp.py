"""Tests for #tbcc:* caption stamps (AyuGram + gatekeeper lane hints)."""

from __future__ import annotations

from app.services.tbcc_caption_stamp import (
    append_tbcc_tags,
    hub_intake_caption,
    merge_quarantine_review_html,
    parse_tbcc_lane_from_caption,
    tbcc_lane_tag,
    tbcc_quarantine_tag,
)


def test_tbcc_lane_tag_normalizes():
    assert tbcc_lane_tag("big_tits") == "#tbcc:big_tits"
    assert tbcc_lane_tag("BIG-TITS") == "#tbcc:big_tits"
    assert tbcc_lane_tag("") == ""


def test_append_tbcc_tags_idempotent():
    cap = append_tbcc_tags("hello", "#tbcc:ass")
    assert cap == "hello #tbcc:ass"
    assert append_tbcc_tags(cap, "#tbcc:ass") == cap


def test_parse_tbcc_lane_from_caption():
    assert parse_tbcc_lane_from_caption("clip #tbcc:milf end") == "milf"
    assert parse_tbcc_lane_from_caption("#tbcc:quarantine") is None
    assert parse_tbcc_lane_from_caption(None) is None


def test_hub_intake_caption():
    assert hub_intake_caption("inbox", "site rip") == "site rip #tbcc:inbox"


def test_quarantine_review_html_suffix():
    html = merge_quarantine_review_html("<b>QUARANTINE</b>", lane_key="voyeur")
    assert "#tbcc:quarantine" in html
    assert "#tbcc:voyeur" in html
    assert tbcc_quarantine_tag() == "#tbcc:quarantine"
