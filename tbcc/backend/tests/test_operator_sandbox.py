"""Operator sandbox — owner-only QA, no public Stars/gate friction."""

from __future__ import annotations

from app.services.companion_access import CompanionAccess
from app.services.operator_sandbox import (
    is_operator_sandbox,
    skip_stars_checkout,
    skip_companion_gate,
)


def test_operator_ids_are_sandbox():
    assert is_operator_sandbox(7787282561)
    assert is_operator_sandbox(8630278848)
    assert is_operator_sandbox(8682971339)
    assert not is_operator_sandbox(999999)


def test_skip_stars_for_operators():
    assert skip_stars_checkout(7787282561) is True
    assert skip_stars_checkout(111) is False


def test_companion_gate_complete_for_operator():
    acc = CompanionAccess(user_id=7787282561, lv_ack=False, member_verified=False)
    assert acc.gate_complete is True


def test_companion_unlimited_allowance_display():
    acc = CompanionAccess(user_id=7787282561, trial_used=5, credits=0)
    assert acc.generations_remaining() == 999


def test_normal_user_gate_not_auto_complete():
    acc = CompanionAccess(user_id=111, lv_ack=False, member_verified=False)
    assert acc.gate_complete is False


def test_skip_companion_gate_matches_operator():
    assert skip_companion_gate(8682971339) is True
    assert skip_companion_gate(42) is False
