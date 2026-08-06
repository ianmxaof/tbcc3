"""Remixer /rebundle command helpers."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from bots import remixer_rebundle as rb


def test_parse_go():
    assert rb._parse_go(["go"]) is True
    assert rb._parse_go(["run"]) is True
    assert rb._parse_go([]) is False
    assert rb._parse_go(["preview"]) is False


def test_cmd_rebundle_rejects_private():
    update = MagicMock()
    update.effective_chat = SimpleNamespace(type="private", id=1)
    update.effective_message = MagicMock()
    update.effective_message.reply_text = AsyncMock()
    ctx = MagicMock()
    ctx.args = []

    async def deny(_u):
        return False

    asyncio.run(rb.cmd_rebundle(update, ctx, deny=deny))
    update.effective_message.reply_text.assert_awaited()
    text = update.effective_message.reply_text.await_args.args[0]
    assert "group" in text.lower()


def test_cmd_rebundle_go_queues_celery():
    update = MagicMock()
    update.effective_chat = SimpleNamespace(type="supergroup", id=-100999)
    msg = MagicMock()
    msg.message_thread_id = 42
    msg.message_id = 7
    msg.reply_text = AsyncMock()
    update.effective_message = msg
    ctx = MagicMock()
    ctx.args = ["go"]
    ctx.bot.get_me = AsyncMock(return_value=SimpleNamespace(id=55))
    ctx.bot.get_chat_member = AsyncMock(
        return_value=SimpleNamespace(status="administrator")
    )

    async def deny(_u):
        return False

    with patch("app.workers.topic_rebundle_worker.rebundle_storage_topic_task") as task:
        task.delay = MagicMock()
        asyncio.run(rb.cmd_rebundle(update, ctx, deny=deny))
        task.delay.assert_called_once()
        kwargs = task.delay.call_args.kwargs
        assert kwargs["channel_ident"] == "-100999"
        assert kwargs["message_thread_id"] == 42
        assert kwargs["allow_partial"] is True
        assert kwargs["dry_run"] is False
        assert kwargs["delete_sources"] is True
