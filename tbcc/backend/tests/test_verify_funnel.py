"""Collab.Land-style verify funnel — deep links, copy, VIP routing."""

from unittest.mock import patch

from app.services.verify_funnel import (
    VERIFY_START_LOOT,
    VERIFY_START_VIP,
    build_loot_room_verify_pin_html,
    parse_verify_start_payload,
    post_verify_response_html,
    verify_deep_link,
    verify_funnel_enabled,
    verify_welcome_html,
)


def test_parse_verify_start_payload():
    assert parse_verify_start_payload(VERIFY_START_VIP) == "vip"
    assert parse_verify_start_payload(VERIFY_START_LOOT) == "loot_room"
    assert parse_verify_start_payload("verify") == "vip"
    assert parse_verify_start_payload("gate_vip") is None


def test_verify_deep_links():
    assert verify_deep_link("vip").endswith(f"?start={VERIFY_START_VIP}")
    assert verify_deep_link("loot_room").endswith(f"?start={VERIFY_START_LOOT}")


def test_welcome_and_pin_copy():
    assert "Tap" in verify_welcome_html("vip")
    assert "Loot Room" in verify_welcome_html("loot_room")
    pin = build_loot_room_verify_pin_html()
    assert VERIFY_START_VIP in pin
    assert "Collab" not in pin
    assert "Gumroad" not in pin


def test_post_verify_vip_upgrade_when_not_subscribed(monkeypatch):
    monkeypatch.setenv("TBCC_VERIFY_FUNNEL_ENABLED", "1")

    class _Db:
        pass

    with patch(
        "app.services.verify_funnel.is_aof_vip_subscriber",
        return_value=False,
    ), patch(
        "app.services.stars_bait_copy.resolve_bait_plan_ids",
        return_value={"subscription": 10, "loot_key": 2, "day_pass": None},
    ):
        html, kb_rows = post_verify_response_html(_Db(), telegram_user_id=999001, target="vip")
    assert "Loot Room" in html
    assert kb_rows is not None
    assert kb_rows[0][0]["url"].startswith("https://t.me/")


def test_post_verify_vip_invite_when_subscribed(monkeypatch):
    class _Db:
        pass

    with patch(
        "app.services.verify_funnel.is_aof_vip_subscriber",
        return_value=True,
    ):
        html, kb_rows = post_verify_response_html(_Db(), telegram_user_id=999002, target="vip")
    assert "active" in html.lower() or "Verified" in html
    assert kb_rows is None


def test_verify_funnel_enabled_default():
    assert verify_funnel_enabled() is True
