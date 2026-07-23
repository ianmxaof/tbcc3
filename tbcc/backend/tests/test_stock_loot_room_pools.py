"""Smoke for LOOT ROOM stock helper lane map / clone uniqueness."""

from __future__ import annotations

from scripts.stock_loot_room_pools import LANE_MAP, _clone_media


def test_lane_map_has_floor_and_vault():
    dests = [d for _, d in LANE_MAP]
    assert any(d.startswith("LOOT ROOM FLOOR") for d in dests)
    assert any("VAULT" in d for d in dests)
    assert len(LANE_MAP) >= 8


def test_clone_media_copies_ids_not_pk(monkeypatch):
    class _M:
        id = 99
        telegram_message_id = 123
        file_id = "fid"
        file_unique_id = "fuid"
        media_type = "photo"
        source_channel = "x"
        tags = "a,b"
        nsfw_tier = "explicit"
        classification_json = None

    row = _clone_media(_M(), 42)
    assert row.id is None or row.id != 99
    assert row.pool_id == 42
    assert row.file_unique_id == "fuid"
    assert row.status == "approved"
