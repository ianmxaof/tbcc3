"""Tests for AOF VIP subscription fulfillment — invite links + channel targeting."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.data.aof_network import AOF_VIP_IDENT, AOF_VIP_INVITE_PRIMARY
from app.services.aof_vip_fulfillment import (
    fulfillment_invite_link,
    vip_primary_invite_url,
    vip_welcome_message_html,
    wire_group_access_plan_to_vip_channel,
)


def test_vip_primary_invite_url_default():
    with patch.dict("os.environ", {}, clear=False):
        assert vip_primary_invite_url() == AOF_VIP_INVITE_PRIMARY


def test_vip_welcome_message_contains_link():
    html = vip_welcome_message_html(invite_link="https://t.me/+Zm7pKVfEgjI4ZDVh")
    assert "AOF VIP" in html
    assert "Zm7pKVfEgjI4ZDVh" in html
    assert "/viproll" in html


def test_fulfillment_invite_link_group_access_plan():
    db = MagicMock()
    plan = MagicMock()
    plan.id = 6
    plan.channel_id = 1

    vip_ch = MagicMock()
    vip_ch.id = 99
    vip_ch.identifier = AOF_VIP_IDENT
    vip_ch.invite_link = AOF_VIP_INVITE_PRIMARY

    with patch("app.services.aof_vip_fulfillment.is_group_access_plan", return_value=True):
        with patch("app.services.aof_vip_fulfillment.vip_channel_row", return_value=vip_ch):
            link = fulfillment_invite_link(db, plan)
    assert link == AOF_VIP_INVITE_PRIMARY


def test_wire_group_access_plan_to_vip_channel_dry_run():
    db = MagicMock()
    vip = MagicMock()
    vip.id = 42
    vip.identifier = AOF_VIP_IDENT
    vip.invite_link = None

    plan = MagicMock()
    plan.id = 6
    plan.name = "AOF Main — 30 days"
    plan.channel_id = 1

    db.query.return_value.filter.return_value.first.side_effect = [vip, plan]
    db.query.return_value.filter.return_value.all.return_value = [plan]

    with patch("app.services.aof_growth_hub.resolve_group_access_plan_id", return_value=6):
        report = wire_group_access_plan_to_vip_channel(db, execute=False)

    assert report.get("ok") is True
    assert report.get("vip_channel_id") == 42
    assert len(report.get("plans") or []) >= 1
