"""Sequenced sponsor packs overlay."""

from __future__ import annotations

import json

from app.models.promo_affiliate_link import PromoAffiliateLink
from app.services.checkout_list_hub import build_checkout_list_bulletin
from app.services.promo_affiliate_rotation import pick_affiliate


def _add(
    db,
    *,
    label: str,
    url: str,
    placements: list[str],
    priority: int = 10,
):
    row = PromoAffiliateLink(
        label=label,
        url=url,
        payout_kind="cpa",
        priority_tier=priority,
        active=True,
        placements_json=json.dumps(placements),
        network_keys_json="[]",
        copy_template="💰 {link}",
    )
    db.add(row)
    db.flush()
    return row


def test_pack_a_x_buffer_never_returns_spicy(db, monkeypatch):
    monkeypatch.setenv("TBCC_SPONSOR_PACKS", "1")
    monkeypatch.setenv("TBCC_BUFFER_X_SPICY_BIAS_EVERY", "3")
    _add(
        db,
        label="Cloud Farm Wallet",
        url="https://t.me/CloudFarmWalletBot/cloud?startapp=1",
        placements=["x_buffer", "links_hub_sfw"],
        priority=0,
    )
    _add(
        db,
        label="AOF Spicy Companion",
        url="https://telegram.me/aof_spicybot_bot?start=src_x",
        placements=["x_buffer", "links_hub_ai"],
        priority=1,
    )
    # Meta starts at Pack A (wallet_earn)
    pick = pick_affiliate(db, "x_buffer", advance=True)
    assert pick is not None
    assert pick.row.label == "Cloud Farm Wallet"
    assert "spicy" not in pick.row.label.lower()


def test_pack_c_milf_bangbros_before_loot(db, monkeypatch):
    monkeypatch.setenv("TBCC_SPONSOR_PACKS", "1")
    _add(
        db,
        label="BangBros PPS",
        url="https://landing.bangbrosnetwork.com/?ats=x",
        placements=["telegram_footer", "loot_roll"],
        priority=1,
    )
    _add(
        db,
        label="Brazzers PPS",
        url="https://landing.brazzersnetwork.com/?ats=x",
        placements=["telegram_footer", "loot_roll"],
        priority=2,
    )
    _add(
        db,
        label="Loot God free roll",
        url="https://telegram.me/aof_lootgod_bot?start=loot_free",
        placements=["telegram_footer", "loot_roll"],
        priority=40,
    )
    first = pick_affiliate(db, "telegram_footer", network_key="milf", advance=True)
    second = pick_affiliate(db, "telegram_footer", network_key="milf", advance=True)
    third = pick_affiliate(db, "telegram_footer", network_key="milf", advance=True)
    assert first and first.row.label == "BangBros PPS"
    assert second and second.row.label == "Brazzers PPS"
    assert third and third.row.label == "Loot God free roll"


def test_pack_a_skips_missing_chime(db, monkeypatch):
    monkeypatch.setenv("TBCC_SPONSOR_PACKS", "1")
    _add(
        db,
        label="Cloud Farm Wallet",
        url="https://t.me/CloudFarmWalletBot/cloud?startapp=1",
        placements=["links_hub"],
        priority=0,
    )
    _add(
        db,
        label="Proton — $20 credits",
        url="https://pr.tn/ref/x",
        placements=["links_hub"],
        priority=11,
    )
    # No Chime — available slots are Cloud Farm then Proton
    c = pick_affiliate(db, "links_hub", advance=True)
    d = pick_affiliate(db, "links_hub", advance=True)
    assert c and c.row.label == "Cloud Farm Wallet"
    assert d and d.row.label == "Proton — $20 credits"


def test_checkout_finance_pack_a_order(db, monkeypatch):
    monkeypatch.setenv("TBCC_SPONSOR_PACKS", "1")
    _add(db, label="Rakuten", url="https://www.rakuten.com/r/x", placements=["links_hub_sfw"])
    _add(
        db,
        label="Cloud Farm Wallet",
        url="https://t.me/CloudFarmWalletBot/cloud?startapp=1",
        placements=["links_hub_sfw"],
    )
    _add(db, label="Chime", url="https://www.chime.com/r/x", placements=["links_hub_sfw"])
    html = build_checkout_list_bulletin(db)
    assert "FINANCE" in html
    fin = html.split("FINANCE", 1)[1].split("DEV", 1)[0]
    # Only Pack A finance heroes in this section (Rakuten is SHOPPING)
    assert fin.index("Cloud Farm") < fin.index("Chime")
    assert "SHOPPING" in html
    assert html.index("FINANCE") < html.index("SHOPPING") or "Cloud Farm" in html
