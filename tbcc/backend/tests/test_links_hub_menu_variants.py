"""Tests for links hub menu variants."""

from pathlib import Path

from app.services.aof_links_hub_menu_variants import (
    AI_VARIANTS,
    CHANNEL_VARIANTS,
    build_ai_inline_buttons,
    build_ai_menu_variant,
    build_all_menu_variants,
    build_channel_inline_buttons,
    build_channel_menu_variant,
    build_interactive_menu_post,
)


def test_motionmuse_seed_has_links_hub_ai():
    seed_path = Path(__file__).resolve().parents[1] / "scripts" / "seed_promo_affiliate_links.py"
    text = seed_path.read_text(encoding="utf-8")
    idx = text.index('"label": "MotionMuse"')
    block = text[idx : idx + 500]
    assert "links_hub_ai" in block


def test_build_all_menu_variants(db):
    menus = build_all_menu_variants(db)
    assert len(menus) == len(CHANNEL_VARIANTS) + len(AI_VARIANTS)
    kinds = {(m.kind, m.variant) for m in menus}
    assert ("channels", "v1") in kinds
    assert ("ai", "v3") in kinds


def test_channel_variant_contains_pipes(db):
    menu = build_channel_menu_variant(db, "v1")
    assert "CONTENT PIPES" in menu.html
    assert "AOF LINK HUB" in menu.html


def test_ai_variant_lists_tools(db, monkeypatch):
    from app.models.promo_affiliate_link import PromoAffiliateLink

    row = PromoAffiliateLink(
        label="MotionMuse",
        url="https://motionmuse.ai/r/wi9rtg3l",
        payout_kind="revshare",
        active=True,
        placements_json='["links_hub_ai"]',
        copy_template="🎬 {link}",
    )
    db.add(row)
    db.commit()

    menu = build_ai_menu_variant(db, "v2")
    assert "MotionMuse" in menu.html


def test_interactive_ai_menu_has_motionmuse_button(db):
    from app.models.promo_affiliate_link import PromoAffiliateLink

    row = PromoAffiliateLink(
        label="MotionMuse",
        url="https://motionmuse.ai/r/wi9rtg3l",
        payout_kind="revshare",
        active=True,
        placements_json='["links_hub_ai"]',
        copy_template="🎬 {link}",
    )
    db.add(row)
    db.commit()

    post = build_interactive_menu_post(db, "ai", "v1")
    flat = [b for row in post.inline_keyboard for b in row]
    labels = [b["text"] for b in flat]
    urls = [b["url"] for b in flat]
    assert any("MotionMuse" in t for t in labels)
    assert any("motionmuse.ai" in u for u in urls)


def test_channel_inline_buttons_count(db):
    rows = build_channel_inline_buttons(db)
    flat = [b for row in rows for b in row]
    pipe_btns = [b for b in flat if b["text"][:2].isdigit()]
    assert len(pipe_btns) == 12
