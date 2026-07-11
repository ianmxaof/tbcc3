"""Checkout caption/button dedupe helpers."""

from app.services.aof_vip_checkout import (
    caption_has_checkout,
    dedupe_url_buttons,
    strip_checkout_caption_lines,
)


def test_strip_bare_vip_footer_link():
    from app.services.aof_vip_checkout import strip_bare_vip_links_from_caption

    footer = (
        'promo\n\n━━━━━━━━━━━━━━━━━━\n'
        '📌 <b>Join the full AOF stack</b> — free lanes via addlist\n'
        '<a href="https://link-target.net/x">addlist all channels</a>'
        ' · ⭐ <a href="https://t.me/+JuO7YRlndFwzYmIx">AOF VIP</a>\n'
        'loot <a href="https://x">aof_lootgod_bot</a>'
    )
    out = strip_bare_vip_links_from_caption(footer)
    assert "t.me/+" not in out
    assert "AOF VIP</a>" not in out
    assert "addlist all channels" in out

    line = '\n💳 <a href="https://t.me/+abc">Subscribe to AOF VIP</a>'
    body = f"goon promo{line}{line}{line}"
    cleaned = strip_checkout_caption_lines(body)
    assert cleaned.count("Subscribe to AOF VIP") == 0
    assert "goon promo" in cleaned


def test_caption_has_checkout_detects_vip_marker():
    assert caption_has_checkout("💳 Subscribe to AOF VIP")
    assert not caption_has_checkout("plain promo only")


def test_dedupe_url_buttons_by_url():
    buttons = [
        {"text": "⭐ Subscribe", "url": "https://t.me/bot?start=c6"},
        {"text": "⭐ Subscribe again", "url": "https://t.me/bot?start=c6"},
        {"text": "Crypto", "url": "https://t.me/bot?start=c6_alt"},
    ]
    out = dedupe_url_buttons(buttons)
    assert len(out) == 2
