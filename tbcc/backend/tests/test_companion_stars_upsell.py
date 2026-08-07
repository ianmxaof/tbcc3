"""Post-delivery Stars upsell + invoice HTTP helpers."""

from __future__ import annotations

import asyncio

import pytest

from app.services import companion_stars as stars


@pytest.fixture(autouse=True)
def _stars_env(monkeypatch):
    monkeypatch.setenv("TBCC_COMPANION_STARS_ENABLED", "1")
    monkeypatch.setenv("TBCC_COMPANION_STARS_PER_PHOTO", "25")
    monkeypatch.setenv("TBCC_COMPANION_BOT_TOKEN", "123:ABC")


def test_maybe_offer_skips_when_allowance_left(monkeypatch):
    class Acc:
        user_id = 2

        def generations_remaining(self):
            return 1

    monkeypatch.setattr("app.services.companion_access.get_access", lambda _uid: Acc())
    called = {"invoice": False}

    async def boom(**_kwargs):
        called["invoice"] = True
        return True

    monkeypatch.setattr(stars, "send_photo_invoice_http", boom)
    ok = asyncio.run(stars.maybe_offer_stars_after_delivery(chat_id=1, user_id=2))
    assert ok is False
    assert called["invoice"] is False


def test_maybe_offer_skips_for_operator():
    ok = asyncio.run(stars.maybe_offer_stars_after_delivery(chat_id=1, user_id=7787282561))
    assert ok is False


def test_maybe_offer_sends_invoice_when_empty(monkeypatch):
    monkeypatch.setenv("TBCC_LOOT_BOT_USERNAME", "aof_lootgod_bot")
    monkeypatch.setenv("TBCC_PAYMENT_BOT_USERNAME", "aofsubscriptions_bot")

    class Acc:
        user_id = 8

        def generations_remaining(self):
            return 0

    monkeypatch.setattr("app.services.companion_access.get_access", lambda _uid: Acc())
    msgs: list[str] = []
    markups: list[dict | None] = []
    invoices: list[dict] = []

    async def fake_msg(*, chat_id, text, parse_mode=None, reply_markup=None):
        msgs.append(text)
        markups.append(reply_markup)
        return True

    async def fake_inv(*, chat_id, user_id):
        invoices.append({"chat_id": chat_id, "user_id": user_id})
        return True

    monkeypatch.setattr(
        "app.services.companion_telegram_dispatch.send_result_message",
        fake_msg,
    )
    monkeypatch.setattr(stars, "send_photo_invoice_http", fake_inv)
    ok = asyncio.run(stars.maybe_offer_stars_after_delivery(chat_id=9, user_id=8))
    assert ok is True
    assert invoices == [{"chat_id": 9, "user_id": 8}]
    assert any("25" in m for m in msgs)
    assert markups[0] is not None
    kb_urls = [
        btn["url"]
        for row in markups[0]["inline_keyboard"]
        for btn in row
    ]
    assert any("loot_free" in u for u in kb_urls)
    assert any("subscribe" in u for u in kb_urls)
