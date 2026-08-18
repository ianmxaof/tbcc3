"""Tests for promo affiliate rotation."""

from __future__ import annotations

import json

from app.models.promo_affiliate_link import PromoAffiliateLink
from app.services.promo_affiliate_rotation import (
    build_sponsor_link_html,
    list_candidates,
    pick_affiliate,
    preview_affiliates,
    resolve_spicy_companion_url,
    row_placements,
)


def _add_row(
    db,
    *,
    label: str,
    url: str,
    placements: list[str],
    network_keys: list[str] | None = None,
    priority: int = 10,
    payout_kind: str = "other",
    payout_detail: str | None = None,
):
    row = PromoAffiliateLink(
        label=label,
        url=url,
        payout_kind=payout_kind,
        payout_detail=payout_detail,
        priority_tier=priority,
        active=True,
        placements_json=json.dumps(placements),
        network_keys_json=json.dumps(network_keys or []),
        copy_template="💰 {link}",
    )
    db.add(row)
    db.flush()
    return row


def test_row_placements_defaults_manual_only(db):
    row = PromoAffiliateLink(label="x", url="https://example.com/a")
    assert row_placements(row) == ["manual_only"]


def test_list_candidates_filters_placement_and_network(db):
    _add_row(
        db,
        label="Musebox",
        url="https://musebox.ai/?ref=test",
        placements=["telegram_footer", "x_buffer"],
        network_keys=["ai"],
        priority=1,
    )
    _add_row(
        db,
        label="Manual",
        url="https://example.com/manual",
        placements=["manual_only"],
        priority=2,
    )
    ai_rows = list_candidates(db, "telegram_footer", network_key="ai")
    assert len(ai_rows) == 1
    assert ai_rows[0].label == "Musebox"
    assert list_candidates(db, "telegram_footer", network_key="bop") == []


def test_pick_affiliate_round_robin(db, monkeypatch):
    monkeypatch.setenv("TBCC_BUFFER_X_SPICY_BIAS_EVERY", "0")
    monkeypatch.setenv("TBCC_SPONSOR_PACKS", "0")
    _add_row(db, label="A", url="https://a.test/1", placements=["x_buffer"], priority=1)
    _add_row(db, label="B", url="https://b.test/1", placements=["x_buffer"], priority=2)
    first = pick_affiliate(db, "x_buffer", advance=True)
    second = pick_affiliate(db, "x_buffer", advance=True)
    third = pick_affiliate(db, "x_buffer", advance=False)
    assert first and second and third
    assert first.row.label == "A"
    assert second.row.label == "B"
    assert third.row.label == "A"


def test_pick_affiliate_spicy_bias_every_third(db, monkeypatch):
    monkeypatch.setenv("TBCC_BUFFER_X_SPICY_BIAS_EVERY", "3")
    monkeypatch.setenv("TBCC_SPONSOR_PACKS", "0")
    _add_row(db, label="A", url="https://a.test/1", placements=["x_buffer"], priority=1)
    _add_row(db, label="B", url="https://b.test/1", placements=["x_buffer"], priority=2)
    _add_row(
        db,
        label="AOF Spicy Companion",
        url="https://telegram.me/aof_spicybot_bot?start=src_companion_promo",
        placements=["x_buffer"],
        priority=5,
    )
    first = pick_affiliate(db, "x_buffer", advance=True)  # idx 0 → bias
    second = pick_affiliate(db, "x_buffer", advance=True)  # idx 1
    third = pick_affiliate(db, "x_buffer", advance=True)  # idx 2
    fourth = pick_affiliate(db, "x_buffer", advance=True)  # idx 0 → bias
    assert first and first.row.label == "AOF Spicy Companion"
    assert second and second.row.label == "B"
    assert third and third.row.label == "AOF Spicy Companion"
    assert fourth and fourth.row.label == "AOF Spicy Companion"


def test_resolve_spicy_companion_url_fallback(monkeypatch):
    monkeypatch.setenv("TBCC_COMPANION_BOT_USERNAME", "aof_spicybot_bot")
    url = resolve_spicy_companion_url(None)
    assert "aof_spicybot_bot" in url
    assert "src_spicy_x" in url


def test_build_sponsor_link_html(db):
    row = _add_row(
        db,
        label="Musebox",
        url="https://musebox.ai/?ref=x",
        placements=["links_hub"],
    )
    html = build_sponsor_link_html(row)
    assert "musebox.ai" in html
    assert "href=" in html


def test_preview_affiliates_order(db):
    _add_row(db, label="A", url="https://a.test/2", placements=["links_hub"], priority=1)
    _add_row(db, label="B", url="https://b.test/2", placements=["links_hub"], priority=2)
    picks = preview_affiliates(db, "links_hub", count=2)
    assert [p["label"] for p in picks] == ["A", "B"]


def test_list_candidates_cash_before_credits(db):
    _add_row(
        db,
        label="Undress credits",
        url="https://nodress.site/tg/bot",
        placements=["x_buffer"],
        priority=1,
        payout_kind="revshare",
        payout_detail="platform_credits",
    )
    _add_row(
        db,
        label="BangBros cash",
        url="https://landing.bangbrosnetwork.com/?ats=x",
        placements=["x_buffer"],
        priority=99,
        payout_kind="pps",
        payout_detail="usd_cash",
    )
    rows = list_candidates(db, "x_buffer")
    assert [r.label for r in rows] == ["BangBros cash", "Undress credits"]
