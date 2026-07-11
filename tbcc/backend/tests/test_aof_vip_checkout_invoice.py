"""Channel post checkout must use invoice/bot links, never bare VIP invites."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.aof_vip_checkout import (
    build_checkout_caption_line,
    checkout_active_for_send,
    is_bare_vip_invite_url,
    merge_checkout_buttons,
    refresh_checkout_caption_for_send,
    resolve_primary_checkout_url,
)


def test_is_bare_vip_invite_matches_subscription_url():
    with patch.dict(
        "os.environ",
        {"TBCC_AOF_VIP_SUBSCRIPTION_INVITE_URL": "https://t.me/+JuO7YRlndFwzYmIx"},
        clear=False,
    ):
        assert is_bare_vip_invite_url("https://t.me/+JuO7YRlndFwzYmIx")
        assert not is_bare_vip_invite_url("https://t.me/$invoice/abc")


@patch("app.services.aof_vip_checkout.create_stars_invoice_link")
@patch("app.services.aof_vip_checkout.use_invoice_link_checkout", return_value=True)
def test_resolve_primary_prefers_invoice_over_vip_invite(mock_use, mock_link):
    mock_link.return_value = "https://t.me/$invoice/test"
    plan = MagicMock()
    plan.is_active = True
    plan.price_stars = 500
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = plan

    with patch.dict(
        "os.environ",
        {
            "TBCC_CHECKOUT_USE_VIP_STAR_SUBSCRIPTION": "1",
            "TBCC_AOF_VIP_SUBSCRIPTION_INVITE_URL": "https://t.me/+JuO7YRlndFwzYmIx",
            "TBCC_PAYMENT_BOT_USERNAME": "aofsubscriptions_bot",
        },
        clear=False,
    ):
        url, kind = resolve_primary_checkout_url(db, 6)
    assert kind == "stars_invoice_link"
    assert url == "https://t.me/$invoice/test"
    assert not is_bare_vip_invite_url(url or "")


def test_single_album_caption_line_empty():
    db = MagicMock()
    assert build_checkout_caption_line(db, 6, multi_album_media=False) == ""


def test_refresh_strips_vip_caption_on_single_album():
    caption = 'promo\n💳 <a href="https://t.me/+abc">Subscribe to AOF VIP</a>'
    db = MagicMock()
    out = refresh_checkout_caption_for_send(
        caption,
        db,
        6,
        multi_album_media=False,
    )
    assert "Subscribe to AOF VIP" not in out
    assert out.strip() == "promo"


@patch("app.services.aof_vip_checkout.create_stars_invoice_link")
@patch("app.services.aof_vip_checkout.use_invoice_link_checkout", return_value=True)
def test_merge_checkout_buttons_use_invoice(mock_use, mock_link):
    mock_link.return_value = "https://t.me/$invoice/abc"
    plan = MagicMock()
    plan.is_active = True
    plan.price_stars = 500
    plan.name = "AOF VIP"
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = plan

    with patch.dict("os.environ", {"TBCC_PAYMENT_BOT_USERNAME": "aofsubscriptions_bot"}, clear=False):
        buttons = merge_checkout_buttons(
            [],
            db,
            checkout_stars_enabled=True,
            checkout_stars_plan_id=6,
            checkout_button_label="Pay ⭐ 500",
            allow_inline_checkout=True,
        )
    assert buttons[0]["url"] == "https://t.me/$invoice/abc"
    assert buttons[0]["text"] == "Pay ⭐ 500"


def test_checkout_followup_uses_deal_stack():
    db = MagicMock()
    plan = MagicMock()
    plan.price_stars = 500
    plan.duration_days = 30
    db.query.return_value.filter.return_value.first.return_value = plan
    from app.services.aof_vip_checkout import checkout_followup_caption_html

    html_out = checkout_followup_caption_html(db, 6)
    assert "Hall Pass" in html_out
    assert "Companion" in html_out or "aof_spicybot" in html_out.lower()
    assert "Pay ⭐" in html_out


def test_checkout_active_for_send_main_group_every_post_by_default():
    from app.data.aof_network import MAIN_GROUP_IDENT

    post = MagicMock()
    post.checkout_stars_enabled = True
    post.checkout_stars_plan_id = 6

    assert checkout_active_for_send(post, MAIN_GROUP_IDENT, caption_slot_index=0) is True
    assert checkout_active_for_send(post, MAIN_GROUP_IDENT, caption_slot_index=1) is True
    with patch.dict("os.environ", {"TBCC_MAIN_GROUP_CHECKOUT_EVERY_N": "2"}):
        assert checkout_active_for_send(post, MAIN_GROUP_IDENT, caption_slot_index=0) is True
        assert checkout_active_for_send(post, MAIN_GROUP_IDENT, caption_slot_index=1) is False
    assert checkout_active_for_send(post, "-1003997525573", caption_slot_index=1) is True
