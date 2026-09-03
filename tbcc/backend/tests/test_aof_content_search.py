"""Tests for AOF keyword search."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.aof_content_search import parse_search_query
from app.services.aof_search_access import album_size_for_tier, resolve_search_tier
from app.services.aof_search_surfaces import allowed_surfaces_for_tier, resolve_surface


def test_parse_search_query_emoji_and_tags():
    parsed = parse_search_query("/find 🍒 pawg office")
    assert "big_tits" in parsed.lane_keys
    assert "ass" in parsed.lane_keys
    assert "office" in parsed.tag_tokens
    assert "🍒" in parsed.emojis_found


def test_parse_search_query_lane_alias():
    parsed = parse_search_query("pinay amateur")
    assert "abg" in parsed.lane_keys


def test_resolve_surface_tiers():
    assert resolve_surface("library", is_vip=False, is_loot_key=False, is_operator=False) is None
    assert resolve_surface("library", is_vip=False, is_loot_key=True, is_operator=False) == "library"
    assert resolve_surface("vip", is_vip=True, is_loot_key=False, is_operator=False) == "vip"
    assert resolve_surface(None, is_vip=True, is_loot_key=False, is_operator=False) == "loot_room"


def test_allowed_surfaces_for_tier():
    assert allowed_surfaces_for_tier(is_vip=False, is_loot_key=False, is_operator=False) == ["loot_room"]
    assert "vip" in allowed_surfaces_for_tier(is_vip=True, is_loot_key=False, is_operator=False)


def test_album_size_for_tier():
    assert album_size_for_tier("free") == 3
    assert album_size_for_tier("loot_key") == 6
    assert album_size_for_tier("vip") == 12


def test_resolve_search_tier_operator(monkeypatch):
    from app.services import aof_search_access as mod

    monkeypatch.setattr(mod, "is_tbcc_operator", lambda _uid: True)
    db = MagicMock()
    assert resolve_search_tier(db, 1) == "operator"


def test_search_approved_media_empty_query():
    from app.services.aof_content_search import search_approved_media

    db = MagicMock()
    out = search_approved_media(db, "   ", surface="loot_room")
    assert out["ok"] is False
    assert out["reason"] == "empty_query"


def test_build_search_result_caption():
    from app.services.aof_search_deliver import build_search_result_caption

    cap = build_search_result_caption(
        {
            "parsed": {"lane_keys": ["milf"], "raw": "milf office"},
            "primary_emoji": "🧜‍♀️",
            "surface": "library",
            "library_link": "https://t.me/c/3790667061/69",
            "items": [{"id": 1}],
        },
        query="milf office",
    )
    assert "milf" in cap.lower()
    assert "Archive of Filth" in cap


def test_macro_fallback_username():
    from app.services.aof_macro_search_router import macro_fallback_username

    assert macro_fallback_username("some_model.name") == "some_model.name"
    assert macro_fallback_username("a b") == ""  # tokens too short for macro username
    assert macro_fallback_username("xgirl99 clips") == "xgirl99"


def test_pick_best_search_surface():
    from app.services.aof_macro_search_router import pick_best_search_surface

    assert pick_best_search_surface({"allowed_surfaces": ["loot_room", "library"]}) == "library"
    assert pick_best_search_surface({"allowed_surfaces": ["loot_room", "library", "vip"]}) == "vip"


def test_parse_category_and_query():
    from bots.macro_search_overlay_ui import parse_category_and_query

    assert parse_category_and_query(["of:alice"]) == ("onlyfans", "alice")
    assert parse_category_and_query(["cams", "bob"]) == ("livecams", "bob")
    assert parse_category_and_query(["model_x"]) == ("macro", "model_x")


def test_get_model_search_sites_for_mode_onlyfans():
    from app.services.model_search_engine import get_model_search_sites_for_mode

    sites = get_model_search_sites_for_mode(mode="onlyfans")
    assert sites
    assert all(s.get("category") == "onlyfans" for s in sites)
