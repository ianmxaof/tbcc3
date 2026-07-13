"""Paid loot-key roll gate + affiliate footer on roll captions."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from app.services.loot_roll_presentation import build_album_caption_html
from app.services.loot_tier_card_assets import resolve_tier_card_path
from app.services.promo_affiliate_rotation import (
    AFFILIATE_PLACEMENTS,
    build_loot_roll_affiliate_footer_html,
)
from app.services.subscription_access import is_aof_vip_subscriber, is_loot_key_holder


def test_loot_roll_placement_registered():
    assert "loot_roll" in AFFILIATE_PLACEMENTS


def test_is_loot_key_holder_loot_section_only():
    sub = MagicMock()
    sub.plan_id = 9
    plan_loot = MagicMock()
    plan_loot.product_type = "subscription"
    plan_loot.bot_section = "loot"
    db = MagicMock()

    with patch("app.services.subscription_access._active_rows", return_value=[sub]):
        db.query.return_value.filter.return_value.first.return_value = plan_loot
        assert is_loot_key_holder(db, 12345) is True
        assert is_aof_vip_subscriber(db, 12345) is False

    plan_main = MagicMock()
    plan_main.product_type = "subscription"
    plan_main.bot_section = "main"
    with patch("app.services.subscription_access._active_rows", return_value=[sub]):
        db.query.return_value.filter.return_value.first.return_value = plan_main
        assert is_loot_key_holder(db, 12345) is False
        assert is_aof_vip_subscriber(db, 12345) is True


def test_album_caption_includes_affiliate_footer():
    preview = {"rarity_tier": 5, "modifier_slot_count": 1}
    out = build_album_caption_html(
        preview,
        modifier_lines=["• bonus — <a href=\"https://example.com\">open</a>"],
        item_count=2,
        affiliate_footer_html='<i>Partner tip — tap <a href="https://x.test">spark</a></i>',
    )
    assert "Partner tip" in out
    assert "https://x.test" in out
    assert "Drip" in out or "World 2-2" in out


def test_affiliate_footer_cycles_loot_roll_then_telegram(monkeypatch):
    row = MagicMock()
    row.label = "Spark AI"
    row.short_url = "https://aff.example/spark"
    row.url = "https://aff.example/spark"
    row.copy_template = None

    pick = MagicMock()
    pick.row = row

    calls: list[str] = []

    def fake_pick(db, placement, *, network_key=None, advance=True):
        calls.append(placement)
        if placement == "loot_roll":
            return None
        if placement == "telegram_footer":
            return pick
        return None

    monkeypatch.setattr(
        "app.services.promo_affiliate_rotation.pick_affiliate",
        fake_pick,
    )
    html = build_loot_roll_affiliate_footer_html(MagicMock(), advance=True)
    assert calls == ["loot_roll", "telegram_footer"]
    assert html is not None
    assert "Spark" in html or "spark" in html.lower()
    assert "https://aff.example/spark" in html


def test_resolve_tier_card_path_finds_file(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("TBCC_LOOT_TIER_CARD_DIR", str(tmp_path))
    assert resolve_tier_card_path(7) is None
    (tmp_path / "tier-7.png").write_bytes(b"fake-png")
    path = resolve_tier_card_path(7)
    assert path is not None
    assert path.name == "tier-7.png"
