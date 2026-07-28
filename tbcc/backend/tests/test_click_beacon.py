"""Click beacon — URL validation, create/hit, public path allowlist."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.middleware.internal_api_auth import path_is_public
from app.models.base import Base
from app.models.click_link import ClickLink, ClickLinkHit
from app.services import click_beacon as cb


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine, tables=[ClickLink.__table__, ClickLinkHit.__table__])
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


def test_public_r_path_allowlisted():
    assert path_is_public("/r/abc123", "GET")
    assert not path_is_public("/r/abc123", "POST")
    assert not path_is_public("/zeus/v1/click-links", "GET")


def test_validate_destination_rejects_bad():
    with pytest.raises(ValueError):
        cb.validate_destination_url("javascript:alert(1)")
    with pytest.raises(ValueError):
        cb.validate_destination_url("ftp://x")
    assert cb.validate_destination_url("https://example.com/x").startswith("https://")


def test_create_and_record_hit(db, monkeypatch):
    monkeypatch.setenv("TBCC_CLICK_BEACON_PUBLIC_BASE", "https://api.example")
    row = cb.create_click_link(db, destination_url="https://t.me/aof_lootgod_bot", label="loot")
    assert row.slug
    assert cb.link_public_url(row) == f"https://api.example/r/{row.slug}"

    hit = cb.record_hit(
        db,
        row,
        ip="1.2.3.4",
        user_agent="TestUA",
        referer=None,
        country="US",
        campaign_id="camp1",
    )
    db.refresh(row)
    assert row.hit_count == 1
    assert hit.ip == "1.2.3.4"
    assert hit.campaign_id == "camp1"


def test_notify_admin_click_calls_inbox(db, monkeypatch):
    monkeypatch.setenv("TBCC_CLICK_BEACON_PUBLIC_BASE", "https://api.example")
    monkeypatch.setenv("TBCC_CLICK_BEACON_NOTIFY_BOTS", "1")
    row = cb.create_click_link(db, destination_url="https://example.com/d", label="x")
    hit = cb.record_hit(
        db,
        row,
        ip="9.9.9.9",
        user_agent="Mozilla/5.0 Chrome",
        referer=None,
        country=None,
        campaign_id="camp42",
    )
    with patch("app.services.admin_inbox.push_admin_inbox_event") as push:
        cb.notify_admin_click(row, hit)
        push.assert_called_once()
        assert push.call_args.kwargs.get("instant") is False
        assert push.call_args.kwargs["meta"]["campaign_id"] == "camp42"


def test_notify_skips_curl_smoke(db, monkeypatch):
    monkeypatch.setenv("TBCC_CLICK_BEACON_NOTIFY_BOTS", "0")
    row = cb.create_click_link(db, destination_url="https://example.com/d", label="x")
    hit = cb.record_hit(
        db, row, ip="1.1.1.1", user_agent="curl/8.2.1", referer=None, country="US", campaign_id=None
    )
    with patch("app.services.admin_inbox.push_admin_inbox_event") as push:
        cb.notify_admin_click(row, hit)
        push.assert_not_called()


def test_is_noise_beacon_user_agent():
    assert cb.is_noise_beacon_user_agent("curl/8.2.1")
    assert cb.is_noise_beacon_user_agent("TelegramBot (like TwitterBot)")
    assert not cb.is_noise_beacon_user_agent("Mozilla/5.0")
