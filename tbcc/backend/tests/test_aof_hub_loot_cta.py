from __future__ import annotations

import os
from types import SimpleNamespace

from app.services.aof_growth_hub import build_addlist_footer, build_links_hub_bulletin
from app.services.aof_network_promo_text import build_mega_pack_readme_text
from app.services.local_media_watermark import ensure_local_watermark_defaults
from app.services.reddit_surface_caption import build_reddit_body


def test_links_hub_bulletin_uses_loot_public_entry(monkeypatch):
    monkeypatch.delenv("TBCC_AOF_PUBLIC_CTA_MODE", raising=False)
    text = build_links_hub_bulletin({}, db=None)

    assert "@aof_lootgod_bot" in text
    assert "Loot Room" in text
    assert "Main Group" not in text
    assert "aofmainhub" not in text


def test_addlist_footer_uses_loot_entry(monkeypatch):
    monkeypatch.delenv("TBCC_AOF_PUBLIC_CTA_MODE", raising=False)
    text = build_addlist_footer({})

    assert "loot bot" in text
    assert "loot room" in text
    assert "aofmainhub" not in text


def test_mega_readme_uses_loot_entry(monkeypatch):
    monkeypatch.delenv("TBCC_WORKINK_BASE_LINK", raising=False)
    text = build_mega_pack_readme_text()

    assert "Loot Bot (first contact)" in text
    assert "Loot Room Group (public commons)" in text
    assert "Main hub" not in text
    assert "Main group" not in text


def test_reddit_direct_policy_uses_loot_entry(monkeypatch):
    monkeypatch.delenv("TBCC_AOF_PUBLIC_CTA_MODE", raising=False)
    profile = SimpleNamespace(link_policy="direct_ok")

    body, comment_link = build_reddit_body(profile)

    assert "Loot entry: https://t.me/aof_lootgod_bot?start=loot_free" in body
    assert "aofmainhub" not in body
    assert comment_link is None


def test_watermark_default_uses_loot_bot(monkeypatch):
    monkeypatch.delenv("TBCC_WATERMARK_TEXT", raising=False)
    ensure_local_watermark_defaults()

    assert os.environ["TBCC_WATERMARK_TEXT"] == "t.me/aof_lootgod_bot"
