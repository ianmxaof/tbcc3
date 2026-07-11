"""UTM tagging for AllMyLinks hub links."""

from __future__ import annotations

import os

import pytest

from app.services.aof_social_links import aof_public_cta_url, fill_armory_template, x_outbound_url
from app.services.erome_promo_wire import build_erome_promo_caption
from app.services.utm_links import allmylinks_tracked_url, append_utm, slug_utm_value


def test_slug_utm_value():
    assert slug_utm_value("A-PL1-TME AOFLOOT") == "a-pl1-tme_aofloot"
    assert slug_utm_value("") == "hub"


def test_append_utm_adds_params(monkeypatch):
    monkeypatch.setenv("TBCC_UTM_ENABLED", "1")
    out = append_utm(
        "https://allmylinks.com/aof69",
        source="buffer",
        medium="x",
        campaign="armory_0",
    )
    assert "utm_source=buffer" in out
    assert "utm_medium=x" in out
    assert "utm_campaign=armory_0" in out


def test_append_utm_preserves_existing(monkeypatch):
    monkeypatch.setenv("TBCC_UTM_ENABLED", "1")
    base = "https://allmylinks.com/aof69?utm_source=custom"
    out = append_utm(base, source="buffer", medium="x", campaign="armory")
    assert "utm_source=custom" in out
    assert "utm_medium=x" in out


def test_append_utm_disabled(monkeypatch):
    monkeypatch.setenv("TBCC_UTM_ENABLED", "0")
    base = "https://allmylinks.com/aof69"
    assert append_utm(base, source="buffer", medium="x", campaign="armory") == base


def test_fill_armory_template_tracks_allmylinks(monkeypatch):
    monkeypatch.setenv("TBCC_UTM_ENABLED", "1")
    monkeypatch.setenv("TBCC_ALLMYLINKS_URL", "https://allmylinks.com/aof69")
    monkeypatch.setenv("TBCC_AOF_GATE_URL", "https://example.com/gate")
    text = fill_armory_template(
        "gate {gate} · map {allmylinks}",
        utm_source="buffer",
        utm_medium="x",
        utm_campaign="taboo",
    )
    assert "utm_source=buffer" in text
    assert "utm_campaign=taboo" in text
    assert "allmylinks.com/aof69" in text


def test_public_x_cta_defaults_to_loot_bot(monkeypatch):
    monkeypatch.delenv("TBCC_X_USE_LINKVERTISE", raising=False)
    monkeypatch.delenv("TBCC_BUFFER_X_OVERFLOW_URL", raising=False)
    monkeypatch.delenv("TBCC_AOF_PUBLIC_CTA_MODE", raising=False)
    monkeypatch.delenv("TBCC_LOOT_BOT_FREE_PULL_URL", raising=False)

    assert aof_public_cta_url() == "https://t.me/aof_lootgod_bot?start=loot_free"
    assert x_outbound_url() == "https://t.me/aof_lootgod_bot?start=loot_free"


def test_fill_armory_template_for_x_uses_loot_entry(monkeypatch):
    monkeypatch.delenv("TBCC_AOF_PUBLIC_CTA_MODE", raising=False)
    monkeypatch.delenv("TBCC_LOOT_BOT_FREE_PULL_URL", raising=False)
    monkeypatch.setenv("TBCC_AOF_HUB_INVITE_URL", "https://t.me/+oldmain")

    text = fill_armory_template("start {hub} · room {loot_room}", for_x=True)

    assert "https://t.me/aof_lootgod_bot?start=loot_free" in text
    assert "https://t.me/+oldmain" not in text


def test_erome_promo_caption_tracks_hub(monkeypatch):
    monkeypatch.setenv("TBCC_UTM_ENABLED", "1")
    monkeypatch.setenv("TBCC_ALLMYLINKS_URL", "https://allmylinks.com/aof69")
    cap = build_erome_promo_caption(
        "https://www.erome.com/a/qrp6kWPY",
        "A-PL1-TME AOFLOOT",
    )
    assert "utm_source=erome" in cap
    assert "utm_medium=album" in cap
    assert "a-pl1-tme_aofloot" in cap
