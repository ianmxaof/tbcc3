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


def _seed_media(db, *, pool_id, tags, file_unique_id):
    from app.models.media import Media

    row = Media(
        telegram_message_id=1,
        file_id="f",
        file_unique_id=file_unique_id,
        media_type="photo",
        source_channel="storage_hub:milf",
        tags=tags,
        pool_id=pool_id,
        status="approved",
    )
    db.add(row)
    db.commit()
    return row


def test_search_approved_media_exclude_ids(db, monkeypatch):
    from app.services.aof_content_search import search_approved_media

    monkeypatch.setenv("TBCC_LOOT_LOCAL_BYTES_ONLY", "0")
    a = _seed_media(db, pool_id=1, tags="office milf", file_unique_id="a")
    _seed_media(db, pool_id=1, tags="office milf", file_unique_id="b")

    out = search_approved_media(db, "office", surface="loot_room", limit=5, pool_ids=[1])
    assert out["ok"] is True
    assert len(out["items"]) == 2

    out2 = search_approved_media(
        db, "office", surface="loot_room", limit=5, pool_ids=[1], exclude_ids=[a.id]
    )
    assert len(out2["items"]) == 1
    assert out2["items"][0]["id"] != a.id


def test_search_approved_media_loosen_drops_tag_filter(db, monkeypatch):
    from app.services.aof_content_search import search_approved_media

    monkeypatch.setenv("TBCC_LOOT_LOCAL_BYTES_ONLY", "0")
    _seed_media(db, pool_id=1, tags="thick pawg", file_unique_id="c")

    tight = search_approved_media(db, "nonexistent_tag_xyz", surface="loot_room", limit=5, pool_ids=[1])
    assert tight["ok"] is False

    loose = search_approved_media(
        db, "nonexistent_tag_xyz", surface="loot_room", limit=5, pool_ids=[1], loosen=True
    )
    assert loose["ok"] is True
    assert loose["loosened"] is True


def test_continue_search_tier1_success_no_tier2_needed(db, monkeypatch):
    from app.services.aof_content_search import continue_search

    monkeypatch.setenv("TBCC_LOOT_LOCAL_BYTES_ONLY", "0")
    _seed_media(db, pool_id=1, tags="office milf", file_unique_id="d")

    out = continue_search(db, "office", surface="loot_room", limit=5, pool_ids=[1])
    assert out["ok"] is True
    assert out.get("loosened") is False
    assert not out.get("vault_pulled")


def test_continue_search_falls_to_tier2_when_tier1_empty(db, monkeypatch):
    from app.services.aof_content_search import continue_search

    monkeypatch.setenv("TBCC_LOOT_LOCAL_BYTES_ONLY", "0")
    _seed_media(db, pool_id=1, tags="thick pawg", file_unique_id="e")

    out = continue_search(db, "nonexistent_tag_xyz", surface="loot_room", limit=5, pool_ids=[1])
    assert out["ok"] is True
    assert out["loosened"] is True


def test_continue_search_tier3_vault_pull_on_full_miss(db, monkeypatch):
    from app.services.aof_content_search import continue_search

    monkeypatch.setenv("TBCC_LOOT_LOCAL_BYTES_ONLY", "0")
    monkeypatch.setenv("TBCC_AOF_SEARCH_TIER3_VAULT", "1")
    # Empty pool 1 — tier1 and tier2 both come up empty.

    def _fake_refill(db_, pool_id, *, need, unpause=False):
        _seed_media(db_, pool_id=pool_id, tags="fresh from vault", file_unique_id="vault-1")
        return 1

    with patch(
        "app.services.sent_vault_lane_refill.refill_pool_from_sent_vault_for_search_sync",
        side_effect=_fake_refill,
    ):
        out = continue_search(db, "anything", surface="loot_room", limit=5, pool_ids=[1])

    assert out["ok"] is True
    assert out.get("vault_pulled") is True


def test_continue_search_tier3_disabled_returns_tier2_result(db, monkeypatch):
    from app.services.aof_content_search import continue_search

    monkeypatch.setenv("TBCC_LOOT_LOCAL_BYTES_ONLY", "0")
    monkeypatch.setenv("TBCC_AOF_SEARCH_TIER3_VAULT", "0")

    with patch(
        "app.services.sent_vault_lane_refill.refill_pool_from_sent_vault_for_search_sync"
    ) as refill:
        out = continue_search(db, "anything", surface="loot_room", limit=5, pool_ids=[1])

    refill.assert_not_called()
    assert out["ok"] is False


def test_aof_search_session_round_trip():
    from app.services import aof_search_session as mod

    store: dict[str, str] = {}

    class _FakeRedis:
        def setex(self, key, ttl, value):
            store[key] = value

        def get(self, key):
            return store.get(key)

    with patch.object(mod, "_redis_client", return_value=_FakeRedis()):
        token = mod.start_search_session(
            user_id=42, surface="loot_room", query="milf office", shown_ids=[1, 2, 3]
        )
        assert token
        session = mod.get_search_session(token)
        assert session["user_id"] == 42
        assert session["shown_ids"] == [1, 2, 3]

        mod.extend_search_session(token, new_shown_ids=[3, 4])
        session2 = mod.get_search_session(token)
        assert session2["shown_ids"] == [1, 2, 3, 4]


def test_aof_search_session_missing_token_returns_none():
    from app.services import aof_search_session as mod

    class _FakeRedis:
        def get(self, key):
            return None

    with patch.object(mod, "_redis_client", return_value=_FakeRedis()):
        assert mod.get_search_session("nope") is None
