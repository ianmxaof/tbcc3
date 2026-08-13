"""Telegram Stars invoice link + payload helpers."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

from unittest.mock import MagicMock, patch

from app.services.telegram_stars_invoice import (
    INVOICE_LINK_USER_ID,
    create_stars_invoice_link,
    stars_invoice_payload,
    use_invoice_link_checkout,
)
from bots.payment_pipeline import parse_invoice_payload, validate_pre_checkout


def test_stars_invoice_payload_shareable_link():
    assert stars_invoice_payload(6, product_type="subscription", user_id=0) == "sub_6_0"
    assert stars_invoice_payload(3, product_type="bundle", user_id=0) == "bundle_3_0"
    assert stars_invoice_payload(9, product_type="companion_credits", user_id=0) == "credits_9_0"


def test_parse_invoice_payload_companion_credits():
    assert parse_invoice_payload("credits_12_42") == ("credits", 12, 42)


def test_parse_invoice_payload_accepts_zero_user():
    assert parse_invoice_payload("sub_6_0") == ("sub", 6, 0)


def test_use_invoice_link_checkout_default_on():
    with patch.dict("os.environ", {}, clear=False):
        assert use_invoice_link_checkout() is True
    with patch.dict("os.environ", {"TBCC_CHECKOUT_USE_INVOICE_LINK": "0"}):
        assert use_invoice_link_checkout() is False


def test_pre_checkout_binds_buyer_when_payload_user_zero():
    class _Q:
        invoice_payload = "sub_6_0"
        currency = "XTR"
        total_amount = 500

        class from_user:
            id = 424242

    async def _plan(_pid: int):
        return {"id": 6, "is_active": True, "product_type": "subscription", "price_stars": 500}

    ok, err = asyncio.run(validate_pre_checkout(_Q(), _plan))
    assert ok is True
    assert err is None


@patch("app.services.telegram_stars_invoice.httpx.Client")
def test_create_stars_invoice_link_caches(mock_client_cls):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"ok": True, "result": "https://t.me/$invoice/abc"}
    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.post.return_value = mock_resp
    mock_client_cls.return_value = mock_client

    plan = {
        "id": 6,
        "name": "AOF Main — 30 days",
        "description": "30-day access",
        "product_type": "subscription",
        "price_stars": 500,
    }
    with patch.dict("os.environ", {"BOT_TOKEN": "test:token"}):
        from app.services import telegram_stars_invoice as mod

        mod._INVOICE_LINK_CACHE.clear()
        link1 = create_stars_invoice_link(plan)
        link2 = create_stars_invoice_link(plan)
    assert link1 == "https://t.me/$invoice/abc"
    assert link2 == link1
    assert mock_client.post.call_count == 1
    body = mock_client.post.call_args[1]["json"]
    assert body["payload"] == f"sub_6_{INVOICE_LINK_USER_ID}"
    assert body["currency"] == "XTR"
