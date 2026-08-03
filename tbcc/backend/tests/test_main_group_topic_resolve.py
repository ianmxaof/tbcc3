"""Loot Room subtopic resolution for sent-cache previews."""

from __future__ import annotations

from app.services.main_group_topic_resolve import (
    build_live_topic_map,
    resolve_loot_room_thread_id,
    verify_loot_room_topic_map,
)


def test_build_live_topic_map_matches_ai_lane():
    live = [
        {"id": 42, "title": "Ai"},
        {"id": 99, "title": "Reception / Party Room"},
    ]
    m = build_live_topic_map(live)
    assert m.get("ai") == 42


def test_resolve_prefers_live_over_stale_static():
    live = [{"id": 5001, "title": "Ai"}]
    tid, source = resolve_loot_room_thread_id("ai", live_topics=live)
    assert tid == 5001
    assert source == "live"


def test_resolve_static_stale_when_id_missing_from_live():
    live = [{"id": 5001, "title": "Ai"}]
    tid, source = resolve_loot_room_thread_id("ass", live_topics=live)
    assert tid is None
    assert source == "static_stale"


def test_verify_flags_static_mismatch():
    live = [{"id": 5001, "title": "Ai"}]
    report = verify_loot_room_topic_map(live_topics=live)
    ai_row = next(r for r in report["mapped"] if r["network_key"] == "ai")
    assert ai_row["live_thread_id"] == 5001
    assert ai_row["static_id_exists_in_group"] is False
