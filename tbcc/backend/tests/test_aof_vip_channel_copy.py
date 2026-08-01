"""VIP channel mirror copy — strip link walls, lane button tree."""

from app.services.aof_growth_hub import FOOTER_MARKER
from app.services.aof_vip_channel_copy import (
    VIP_PACING_ADMONITION,
    build_vip_navigation_buttons,
    pick_vip_mirror_caption,
    strip_vip_affiliate_blocks,
)


class _FakePost:
    def __init__(self, content=None, variations=None, idx=0):
        self.content = content
        self.content_variations = variations
        self.caption_rotation_index = idx

    def get_content_variations(self):
        return self.content_variations


def test_strip_bulletin_returns_empty():
    bulletin = "📌 <b>AOF LINKS HUB</b>\nCentral hub\n📂 <b>CONTENT</b>\n👉 lane"
    assert strip_vip_affiliate_blocks(bulletin) == ""


def test_strip_footer_keeps_lane_promo():
    promo = (
        "🔥 <b>AOF ASS</b> — heavy curve lane.\n"
        f"━━━━━━━━━━━━━━━━━━\n📌 <b>{FOOTER_MARKER}</b>\naddlist"
    )
    out = strip_vip_affiliate_blocks(promo)
    assert "AOF ASS" in out
    assert FOOTER_MARKER not in out


def test_pick_vip_mirror_skips_bulletin_slot():
    bulletin = "📌 <b>AOF LINKS HUB</b>\nwall of links"
    promo = "🔥 <b>AOF BIG TITS</b> — stacked lane."
    post = _FakePost(variations=[bulletin, promo], idx=0)
    out = pick_vip_mirror_caption(post, None)
    assert "BIG TITS" in out
    assert "LINKS HUB" not in out


def test_pick_vip_mirror_fallback_admonition():
    post = _FakePost(content="📌 <b>AOF LINKS HUB</b>\nonly links")
    out = pick_vip_mirror_caption(post, None)
    assert out == VIP_PACING_ADMONITION


def test_build_vip_navigation_buttons_has_rows(monkeypatch):
    monkeypatch.setattr(
        "app.services.aof_growth_hub.lv_urls",
        lambda db: {
            "big_tits": "https://t.me/+bt",
            "ass": "https://t.me/+ass",
            "addlist": "https://t.me/addlist",
        },
    )
    rows = build_vip_navigation_buttons(None)
    assert rows
    flat = [b for row in rows for b in row]
    assert any("All lanes" in b["text"] for b in flat)
