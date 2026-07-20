"""Legacy checkout plan id remapping (retired plan 6 → active VIP ladder)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.aof_vip_checkout import (
    CHECKOUT_CAPTION_LABEL_DEFAULT,
    build_checkout_caption_line,
    normalize_checkout_plan_id,
)


def test_normalize_checkout_plan_id_maps_inactive_legacy():
    db = MagicMock()
    inactive = MagicMock(is_active=False, price_stars=500)
    db.query.return_value.filter.return_value.first.return_value = inactive

    with patch("app.services.aof_growth_hub.resolve_group_access_plan_id", return_value=10):
        assert normalize_checkout_plan_id(db, 6) == 10


def test_normalize_checkout_plan_id_keeps_active_plan():
    db = MagicMock()
    active = MagicMock(is_active=True, price_stars=500)
    db.query.return_value.filter.return_value.first.return_value = active
    assert normalize_checkout_plan_id(db, 10) == 10


def test_build_checkout_caption_uses_menu_deep_link(monkeypatch):
    monkeypatch.setenv("TBCC_PAYMENT_BOT_USERNAME", "aofsubscriptions_bot")
    db = MagicMock()
    active = MagicMock(is_active=True, price_stars=500)
    db.query.return_value.filter.return_value.first.return_value = active

    line = build_checkout_caption_line(db, 10, multi_album_media=True)
    assert CHECKOUT_CAPTION_LABEL_DEFAULT in line
    assert "start=cm10" in line
    assert "start=c10" not in line
