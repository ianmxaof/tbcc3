"""Pack browser helpers — parse, ownership, stats."""

from __future__ import annotations

from bots.pack_browser import (
    pack_stats_line,
    pack_zip_part_count,
    parse_pack_browser_callback,
    parse_pack_start_payload,
    user_owns_plan,
)


def test_parse_pack_start_payload():
    assert parse_pack_start_payload("pack_12") == 12
    assert parse_pack_start_payload("pack12") == 12
    assert parse_pack_start_payload("pack-7") == 7
    assert parse_pack_start_payload("subscribe") is None


def test_user_owns_plan_active_match():
    subs = [{"status": "active", "plan_id": 5}, {"status": "expired", "plan_id": 3}]
    assert user_owns_plan(subs, 5) is True
    assert user_owns_plan(subs, 3) is False


def test_pack_zip_part_count_from_parts_list():
    plan = {"bundle_zip_parts": ["a.zip", "b.zip"]}
    assert pack_zip_part_count(plan) == 2


def test_pack_stats_line():
    plan = {"price_stars": 250, "bundle_zip_parts": ["x.zip"], "promo_image_urls": ["https://a/b.jpg"]}
    line = pack_stats_line(plan)
    assert "250" in line
    assert "zip" in line


def test_parse_pack_browser_callback():
    assert parse_pack_browser_callback("pb:cat") == {"action": "catalog"}
    assert parse_pack_browser_callback("pb:d:9") == {
        "action": "detail",
        "plan_id": 9,
        "page": 0,
        "filter": "a",
    }
    assert parse_pack_browser_callback("pb:pv:9:1:i") == {
        "action": "preview",
        "plan_id": 9,
        "page": 1,
        "filter": "i",
    }
    assert parse_pack_browser_callback("pb:dl:9") == {"action": "download", "plan_id": 9}
    assert parse_pack_browser_callback("menu_packs") is None


def test_pack_stats_line_uses_summary():
    plan = {
        "price_stars": 250,
        "pack_asset_summary": {"video": 12, "image": 24, "other": 0, "total": 36, "previews": 18},
    }
    line = pack_stats_line(plan)
    assert "12 video" in line
    assert "24 image" in line
    assert "Total: 36" in line
