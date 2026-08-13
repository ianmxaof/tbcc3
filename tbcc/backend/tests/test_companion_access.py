"""Tests for companion_access gate + credit logic."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services import companion_access as ca


@pytest.fixture(autouse=True)
def _clear_mem(monkeypatch):
    ca._MEM.clear()
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setenv("TBCC_COMPANION_GATE_ENABLED", "1")
    monkeypatch.setenv("TBCC_COMPANION_FREE_TRIAL_PHOTOS", "1")
    monkeypatch.delenv("ADMIN_TELEGRAM_ID", raising=False)
    monkeypatch.delenv("TBCC_COMPANION_ADMIN_IDS", raising=False)


def test_gate_incomplete_blocks_api_spend():
    uid = 12345
    ok, reason = ca.can_spend_operator_api(uid)
    assert not ok
    assert reason == "complete_gate"


def test_gate_complete_with_trial_allows_spend():
    uid = 999
    acc = ca.get_access(uid)
    acc.lv_ack = True
    acc.member_verified = True
    ca.save_access(acc)
    ok, reason = ca.can_spend_operator_api(uid)
    assert ok
    assert reason == "allowance"


def test_consume_and_refund_trial():
    uid = 42
    acc = ca.get_access(uid)
    acc.lv_ack = True
    acc.member_verified = True
    ca.save_access(acc)
    ok, referral_credit = ca.consume_generation_allowance(uid)
    assert ok
    assert ca.get_access(uid).generations_remaining() == 0
    ca.refund_generation_allowance(uid)
    assert ca.get_access(uid).generations_remaining() == 1


@pytest.mark.asyncio
async def test_verify_membership_marks_access(monkeypatch):
    uid = 555
    acc = ca.get_access(uid)
    acc.lv_ack = True
    ca.save_access(acc)

    member = MagicMock()
    member.status = ca.ChatMemberStatus.MEMBER
    bot = AsyncMock()
    bot.get_chat_member = AsyncMock(return_value=member)

    ok, name = await ca.verify_aof_membership(bot, uid)
    assert ok
    assert name
    assert ca.get_access(uid).member_verified


@pytest.mark.asyncio
async def test_auto_complete_gate_retries_membership():
    uid = 777
    acc = ca.get_access(uid)
    acc.lv_ack = True
    ca.save_access(acc)

    member = MagicMock()
    member.status = ca.ChatMemberStatus.MEMBER
    bot = AsyncMock()
    bot.get_chat_member = AsyncMock(return_value=member)

    out = await ca.auto_complete_gate_if_ready(bot, uid)
    assert out.gate_complete
    assert out.member_verified
    bot.get_chat_member.assert_called()
