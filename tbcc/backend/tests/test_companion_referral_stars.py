"""Tests for companion referral + Stars helpers."""

from __future__ import annotations

import pytest

from app.services import companion_referral as ref
from app.services import companion_stars as stars
from app.services.companion_access import get_access, save_access


@pytest.fixture(autouse=True)
def _clear(monkeypatch):
    ref._MEM_CODES.clear()
    ref._MEM_USER_CODE.clear()
    ref._MEM_PENDING.clear()
    ref._MEM_CREDITED.clear()
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setenv("TBCC_COMPANION_REFERRAL_ENABLED", "1")
    monkeypatch.setenv("TBCC_COMPANION_REFERRAL_BONUS_PHOTOS", "1")
    monkeypatch.setenv("TBCC_COMPANION_GATE_ENABLED", "1")


def test_referral_credit_on_gate_complete():
    referrer = 100
    referred = 200
    ref.ensure_referral_code(referrer)
    code = ref.ensure_referral_code(referrer)
    assert ref.record_referral_by_code(referred_user_id=referred, code=code)

    acc = get_access(referred)
    acc.lv_ack = True
    acc.member_verified = True
    save_access(acc)

    result = ref.maybe_credit_referrer_on_gate_complete(referred)
    assert result is not None
    assert result["referrer_user_id"] == referrer
    assert result["bonus_granted"] == 1
    assert ref.maybe_credit_referrer_on_gate_complete(referred) is None


def test_stars_validate_pre_checkout(monkeypatch):
    monkeypatch.setenv("TBCC_COMPANION_STARS_PER_PHOTO", "25")
    payload = stars.invoice_payload(4242)
    ok, err = stars.validate_pre_checkout(
        invoice_payload_raw=payload,
        buyer_user_id=4242,
        currency="XTR",
        total_amount=25,
    )
    assert ok is True
    assert err == ""
    bad, err2 = stars.validate_pre_checkout(
        invoice_payload_raw=payload,
        buyer_user_id=9999,
        currency="XTR",
        total_amount=25,
    )
    assert bad is False


def test_parse_invoice_payload():
    assert stars.parse_invoice_payload("companion_photo_123") == 123
    assert stars.parse_invoice_payload("sub_1_0") is None
