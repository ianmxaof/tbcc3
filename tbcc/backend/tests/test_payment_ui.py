"""Payment bot single-anchor menu helpers."""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from unittest.mock import AsyncMock, MagicMock

from bots.payment_ui import BACK_BUTTON, MENU_HOME, with_back_row


def test_with_back_row_appends_main_menu_button():
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("Packs", callback_data="menu_packs")]])
    out = with_back_row(kb)
    assert out.inline_keyboard[-1][0].text == BACK_BUTTON.text
    assert out.inline_keyboard[-1][0].callback_data == MENU_HOME


def test_with_back_row_on_empty_markup():
    out = with_back_row(None)
    assert len(out.inline_keyboard) == 1
    assert out.inline_keyboard[0][0].callback_data == MENU_HOME


def test_set_anchor_uses_chat_data_when_user_data_missing():
    from bots.payment_ui import PAY_UI_ANCHOR_KEY, set_anchor

    context = MagicMock()
    context.user_data = None
    context.chat_data = {}

    set_anchor(context, chat_id=-100123, message_id=55, kind="text")

    assert context.chat_data[PAY_UI_ANCHOR_KEY]["message_id"] == 55


def test_set_anchor_noop_when_both_stores_missing():
    from bots.payment_ui import set_anchor

    context = MagicMock()
    context.user_data = None
    context.chat_data = None

    set_anchor(context, chat_id=-100123, message_id=55, kind="text")  # must not raise


def test_clear_preview_album_deletes_tracked_messages():
    import asyncio
    from unittest.mock import AsyncMock, MagicMock

    from bots.payment_ui import PAY_UI_ALBUM_KEY, clear_preview_album

    bot = MagicMock()
    bot.delete_message = AsyncMock()
    context = MagicMock()
    context.user_data = {
        PAY_UI_ALBUM_KEY: {"chat_id": 42, "message_ids": [101, 102]},
    }

    asyncio.run(clear_preview_album(bot, context, chat_id=42))

    assert bot.delete_message.await_count == 2
    bot.delete_message.assert_any_await(chat_id=42, message_id=101)
    bot.delete_message.assert_any_await(chat_id=42, message_id=102)
    assert PAY_UI_ALBUM_KEY not in context.user_data
