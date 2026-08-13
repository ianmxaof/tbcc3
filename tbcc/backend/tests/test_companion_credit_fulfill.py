"""Companion credit pack fulfillment tests."""

from unittest.mock import patch

import pytest

from app.data.companion_credit_packs import COMPANION_CREDIT_PACKS
from app.services.companion_access import get_access, save_access
from app.services.companion_credit_fulfill import grant_companion_credit_pack, is_companion_credit_plan


class _Plan:
    def __init__(self, *, name: str, product_type: str = "companion_credits", id: int = 1):
        self.id = id
        self.name = name
        self.product_type = product_type


def test_is_companion_credit_plan():
    pack = COMPANION_CREDIT_PACKS[0]
    assert is_companion_credit_plan(_Plan(name=pack.plan_name))
    assert not is_companion_credit_plan(_Plan(name="Other", product_type="subscription"))


def test_grant_companion_credit_pack(monkeypatch):
    monkeypatch.setenv("TBCC_COMPANION_CREDIT_PACKS_ENABLED", "1")
    pack = COMPANION_CREDIT_PACKS[0]
    uid = 991_001_123
    acc = get_access(uid)
    acc.credits = 0
    acc.trial_used = 1
    save_access(acc)

    plan = _Plan(name=pack.plan_name, id=42)

    class _Q:
        def filter(self, *a, **k):
            return self

        def first(self):
            return plan

    class _DB:
        def query(self, *a, **k):
            return _Q()

    with patch("app.services.companion_credit_fulfill._already_granted", return_value=False), patch(
        "app.services.companion_credit_fulfill._mark_granted"
    ):
        result = grant_companion_credit_pack(_DB(), uid, 42, charge_id="test-charge-1")
    assert result["ok"] is True
    assert result["credits_granted"] == pack.credit_units
    assert get_access(uid).credits == pack.credit_units
