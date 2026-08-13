"""Affiliate outbound URLs wrapped in click beacons when enabled."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import pytest

from app.models.base import Base
from app.models.click_link import ClickLink, ClickLinkHit
from app.models.promo_affiliate_link import PromoAffiliateLink
from app.services.affiliate_beacon_wrap import wrap_affiliate_outbound_url


@pytest.fixture()
def db(monkeypatch):
    monkeypatch.setenv("TBCC_CLICK_BEACON_PUBLIC_BASE", "https://api.example")
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        bind=engine,
        tables=[ClickLink.__table__, ClickLinkHit.__table__, PromoAffiliateLink.__table__],
    )
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


def test_wrap_returns_beacon_url(db, monkeypatch):
    monkeypatch.setenv("TBCC_AFFILIATE_BEACON_WRAP", "1")
    row = PromoAffiliateLink(label="Test Wallet", url="https://t.me/ExampleBot")
    out = wrap_affiliate_outbound_url(db, row, placement="loot_roll")
    assert out.startswith("https://api.example/r/aff-")


def test_wrap_rewrites_attribution_start_to_placement_ref(db, monkeypatch):
    monkeypatch.setenv("TBCC_AFFILIATE_BEACON_WRAP", "1")
    row = PromoAffiliateLink(
        label="AOF Spicy Companion",
        url="https://telegram.me/aof_spicybot_bot?start=src_companion_promo",
    )
    out = wrap_affiliate_outbound_url(db, row, placement="x_buffer")
    assert out.startswith("https://api.example/r/aff-")
    link = db.query(ClickLink).first()
    assert link is not None
    assert link.source_ref == "src_aff_aof_spicy_companion_x_buffer"
    # Bot /start payload now matches the click source_ref → funnel join works.
    assert link.destination_url == (
        "https://telegram.me/aof_spicybot_bot?start=src_aff_aof_spicy_companion_x_buffer"
    )


def test_wrap_leaves_product_start_payload_alone(db, monkeypatch):
    monkeypatch.setenv("TBCC_AFFILIATE_BEACON_WRAP", "1")
    row = PromoAffiliateLink(
        label="Loot God free roll",
        url="https://telegram.me/aof_lootgod_bot?start=loot_free",
    )
    wrap_affiliate_outbound_url(db, row, placement="telegram_footer")
    link = db.query(ClickLink).first()
    assert link is not None
    assert link.destination_url == "https://telegram.me/aof_lootgod_bot?start=loot_free"


def test_wrap_ignores_non_telegram_urls(db, monkeypatch):
    monkeypatch.setenv("TBCC_AFFILIATE_BEACON_WRAP", "1")
    url = "https://example.com/landing?start=src_should_not_change"
    row = PromoAffiliateLink(label="External", url=url)
    wrap_affiliate_outbound_url(db, row, placement="x_buffer")
    link = db.query(ClickLink).first()
    assert link is not None
    assert link.destination_url == url
