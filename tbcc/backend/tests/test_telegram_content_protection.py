"""Tests for telegram content protection helpers."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import patch

from app.services.telegram_content_protection import (
    bot_protect_content_kw,
    channel_protect_content_enabled,
    telethon_protect_context,
)


def test_channel_protect_content_default_on():
    with patch.dict("os.environ", {}, clear=False):
        import os

        os.environ.pop("TBCC_CHANNEL_PROTECT_CONTENT", None)
        assert channel_protect_content_enabled() is True


def test_bot_protect_content_kw_when_enabled():
    with patch(
        "app.services.telegram_content_protection.channel_protect_content_enabled",
        return_value=True,
    ):
        assert bot_protect_content_kw() == {"protect_content": True}


def test_telethon_protect_context_injects_noforwards():
    from telethon.tl.functions.messages import SendMessageRequest

    client = SimpleNamespace()
    captured = {}

    async def original_call(request, ordered=False, flood_sleep_threshold=None):
        captured["request"] = request
        return "ok"

    client.__call__ = original_call
    req = SendMessageRequest(peer=0, message="hi", random_id=1)

    async def _run():
        with patch(
            "app.services.telegram_content_protection.channel_protect_content_enabled",
            return_value=True,
        ):
            async with telethon_protect_context(client):
                await client.__call__(req)

    asyncio.run(_run())
    assert captured["request"].noforwards is True
