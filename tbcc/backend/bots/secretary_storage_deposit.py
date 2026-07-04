"""Secretary bot wrapper — /deposit disabled; Album Composer handles Storage Hub deposits."""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from app.services.storage_topic_deposit import storage_hub_chat_id_int
from bots.storage_hub_deposit_bot import cmd_deposit as _cmd_deposit
from bots.storage_hub_deposit_bot import secretary_storage_deposit_enabled


async def cmd_deposit(update: Update, context: ContextTypes.DEFAULT_TYPE, *, is_admin: bool) -> None:
    # Silent in Storage Hub — Album Composer (remixer) owns /deposit there.
    chat = update.effective_chat
    if chat and int(chat.id) == storage_hub_chat_id_int():
        if not secretary_storage_deposit_enabled():
            return
    elif not secretary_storage_deposit_enabled():
        return
    await _cmd_deposit(update, context, bot_label="secretary")
