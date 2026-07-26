"""UTM tagging for AllMyLinks hub links."""

from __future__ import annotations

import os

import pytest

from app.services.aof_social_links import fill_armory_template
from app.services.erome_promo_wire import build_erome_promo_caption
from app.services.utm_links import allmylinks_tracked_url, append_utm, slug_utm_value


def test_slug_utm_value():
    assert slug_utm_value("A-PL1-TME AOFMAINHUB") == "a-pl1-tme_aofmainhub"
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


def test_erome_promo_caption_tracks_hub(monkeypatch):
    monkeypatch.setenv("TBCC_UTM_ENABLED", "1")
    monkeypatch.setenv("TBCC_ALLMYLINKS_URL", "https://allmylinks.com/aof69")
    cap = build_erome_promo_caption(
        "https://www.erome.com/a/qrp6kWPY",
        "A-PL1-TME AOFMAINHUB",
    )
    assert "utm_source=erome" in cap
    assert "utm_medium=album" in cap
    assert "a-pl1-tme_aofmainhub" in cap


def test_gumroad_vip_url_default(monkeypatch):
    from app.services.aof_social_links import gumroad_vip_url

    monkeypatch.delenv("TBCC_GUMROAD_PRODUCT_URL", raising=False)
    assert gumroad_vip_url() == "https://aof69.gumroad.com/l/ynnulc"


def test_fill_armory_template_gumroad_vip(monkeypatch):
    monkeypatch.setenv("TBCC_GUMROAD_PRODUCT_URL", "https://aof69.gumroad.com/l/ynnulc")
    monkeypatch.setenv("TBCC_AOF_GATE_URL", "https://example.com/gate")
    text = fill_armory_template("VIP {gumroad_vip} · hub {hub}", for_x=True)
    assert "https://aof69.gumroad.com/l/ynnulc" in text


def test_append_gumroad_vip_variations():
    from app.services.aof_growth_hub import _append_gumroad_vip_variations

    footer = "\n\n━━━━━━━━━━━━━━━━━━\n📌 Join the full AOF stack"
    base = ["⭐ promo" + footer]
    out = _append_gumroad_vip_variations(base, footer)
    assert len(out) > len(base)
    assert any("gumroad.com/l/ynnulc" in v for v in out)
