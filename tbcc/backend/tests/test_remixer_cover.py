"""Remixer Cover mode — toggle + copy_message path (mocked Bot API)."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from bots import remixer_cover as cover


def _ctx(*, cover_on: bool = False) -> MagicMock:
    ctx = MagicMock()
    ctx.chat_data = {cover.COVER_MODE_KEY: cover_on} if cover_on else {}
    ctx.bot = MagicMock()
    ctx.bot.copy_message = AsyncMock(return_value=SimpleNamespace(message_id=42))
    return ctx


def test_cover_toggle_commands():
    update = MagicMock()
    update.effective_message = MagicMock()
    update.effective_message.reply_text = AsyncMock()
    ctx = _ctx()

    async def deny(_u):
        return False

    async def run():
        await cover.cmd_cover(update, ctx, deny=deny)
        assert cover.is_cover_mode(ctx) is True
        await cover.cmd_compose(update, ctx, deny=deny)
        assert cover.is_cover_mode(ctx) is False

    asyncio.run(run())


def test_echo_cover_uses_copy_message():
    update = MagicMock()
    update.effective_chat = SimpleNamespace(id=111)
    update.effective_user = SimpleNamespace(id=7)
    update.effective_message = SimpleNamespace(
        message_id=9,
        has_protected_content=False,
        reply_text=AsyncMock(),
        text="hi",
    )
    ctx = _ctx(cover_on=True)

    mid = asyncio.run(cover.echo_cover_message(update, ctx))
    assert mid == 42
    ctx.bot.copy_message.assert_awaited_once()
    kwargs = ctx.bot.copy_message.await_args.kwargs
    assert kwargs["chat_id"] == 111
    assert kwargs["from_chat_id"] == 111
    assert kwargs["message_id"] == 9
    assert ctx.chat_data[cover.COVER_LAST_MSG_KEY] == 42


def test_handle_cover_inbound_skips_when_off():
    update = MagicMock()
    ctx = _ctx(cover_on=False)

    async def deny(_u):
        return False

    handled = asyncio.run(
        cover.handle_cover_inbound(
            update, ctx, deny=deny, channel_id=None, channel_name=""
        )
    )
    assert handled is False


def test_send_last_cover_to_channel():
    update = MagicMock()
    update.effective_chat = SimpleNamespace(id=111)
    update.callback_query = MagicMock()
    update.callback_query.answer = AsyncMock()
    update.callback_query.message = MagicMock()
    update.callback_query.message.reply_text = AsyncMock()
    ctx = _ctx()
    ctx.chat_data[cover.COVER_LAST_MSG_KEY] = 42
    ctx.bot.copy_message = AsyncMock(return_value=SimpleNamespace(message_id=99))

    asyncio.run(
        cover.send_last_cover_to_channel(
            update, ctx, channel_id=-1001, channel_name="Promo"
        )
    )
    ctx.bot.copy_message.assert_awaited_once()
    assert ctx.bot.copy_message.await_args.kwargs["chat_id"] == -1001
    assert ctx.bot.copy_message.await_args.kwargs["message_id"] == 42
