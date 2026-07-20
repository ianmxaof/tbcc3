"""Gumroad Ping parsing + checkout URL helpers."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.gumroad_ping import (
    append_tbcc_ref,
    extract_tbcc_ref,
    extract_telegram_user_id,
    form_body_to_dict,
    income_usd_from_payload,
    resolve_plan_id_from_payload,
    sale_charge_id,
    verify_seller,
)


def test_append_tbcc_ref():
    url = append_tbcc_ref("https://aof69.gumroad.com/l/vip30", "EPO-ABCDEF123456")
    assert "tbcc_ref=EPO-ABCDEF123456" in url
    assert url.startswith("https://aof69.gumroad.com/l/vip30")


def test_extract_tbcc_ref_from_url_params_pythonish():
    payload = {
        "url_params": "{'tbcc_ref': 'EPO-AABBCCDDEEFF', 'source': 'bot'}",
    }
    assert extract_tbcc_ref(payload) == "EPO-AABBCCDDEEFF"


def test_extract_tbcc_ref_from_json_url_params():
    payload = {"url_params": '{"tbcc_ref": "EPO-112233445566"}'}
    assert extract_tbcc_ref(payload) == "EPO-112233445566"


def test_extract_telegram_user_id_custom_fields():
    payload = {"custom_fields": {"Telegram ID": "7787282561"}}
    assert extract_telegram_user_id(payload) == 7787282561


def test_resolve_plan_id_from_permalink(monkeypatch):
    monkeypatch.setenv(
        "TBCC_GUMROAD_PRODUCT_MAP",
        '{"vip30": 6, "https://aof69.gumroad.com/l/vip30": 6}',
    )
    assert resolve_plan_id_from_payload({"product_permalink": "https://aof69.gumroad.com/l/vip30"}) == 6
    assert resolve_plan_id_from_payload({"permalink": "vip30"}) == 6


def test_verify_seller(monkeypatch):
    monkeypatch.setenv("TBCC_GUMROAD_SELLER_ID", "seller_abc")
    assert verify_seller({"seller_id": "seller_abc"}) is True
    assert verify_seller({"seller_id": "other"}) is False


def test_income_usd_cents():
    assert income_usd_from_payload({"price": "999"}) == 9.99


def test_sale_charge_id():
    assert sale_charge_id({"sale_id": "SALE1"}, "EPO-ABC").startswith("gumroad_SALE1_")


def test_form_body_to_dict_from_mapping():
    assert form_body_to_dict({"email": "a@b.c", "price": "100"})["email"] == "a@b.c"


def test_gumroad_webhook_epo_path(monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import app

    monkeypatch.setenv("TBCC_GUMROAD_SELLER_ID", "seller_xyz")

    order = MagicMock()
    order.id = 42
    order.reference_code = "EPO-AABBCCDDEEFF"
    order.status = "pending"

    with patch("app.api.webhooks_payment.fulfill_external_order") as fulfill:
        fulfill.return_value = {"ok": True, "subscription_id": 1}
        with patch("app.api.webhooks_payment.get_db") as gdb:
            # Override dependency via app — use TestClient with form data
            pass

    # Unit-level: call endpoint logic pieces already covered; hit API with dependency override
    from app.database.session import get_db
    from app.api import webhooks_payment as wh

    def _db():
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = order
        yield db

    app.dependency_overrides[get_db] = _db
    try:
        with patch.object(wh, "fulfill_external_order", return_value={"ok": True}) as fulfill:
            client = TestClient(app)
            r = client.post(
                "/webhooks/gumroad",
                data={
                    "seller_id": "seller_xyz",
                    "sale_id": "sale99",
                    "price": "1999",
                    "url_params": "{'tbcc_ref': 'EPO-AABBCCDDEEFF'}",
                    "refunded": "false",
                },
            )
            assert r.status_code == 200, r.text
            body = r.json()
            assert body.get("ok") is True
            assert body.get("fulfilled") == 42 or body.get("idempotent")
            fulfill.assert_called_once()
            assert fulfill.call_args.kwargs.get("payment_method") == "gumroad"
    finally:
        app.dependency_overrides.pop(get_db, None)
