"""Remixer Cover mode — ForwardsCover-style echo (no forward header) via copy_message."""

from __future__ import annotations

import logging
import time

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.error import BadRequest, Forbidden
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

COVER_MODE_KEY = "remixer_cover_mode"
COVER_LAST_MSG_KEY = "remixer_cover_last_message_id"
_RATE: dict[int, float] = {}
_RATE_MIN_INTERVAL_S = 0.35


def is_cover_mode(context: ContextTypes.DEFAULT_TYPE) -> bool:
    return bool(context.chat_data.get(COVER_MODE_KEY))


def set_cover_mode(context: ContextTypes.DEFAULT_TYPE, enabled: bool) -> None:
    context.chat_data[COVER_MODE_KEY] = bool(enabled)


def _rate_ok(user_id: int) -> bool:
    now = time.monotonic()
    last = _RATE.get(user_id, 0.0)
    if now - last < _RATE_MIN_INTERVAL_S:
        return False
    _RATE[user_id] = now
    return True


def cover_keyboard(*, has_channel: bool) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton("🔁 Echo again", callback_data="ac:cover:echo"),
            InlineKeyboardButton("✏️ Compose mode", callback_data="ac:cover:off"),
        ]
    ]
    if has_channel:
        rows.insert(
            0,
            [InlineKeyboardButton("📤 Send covered → channel", callback_data="ac:cover:sendch")],
        )
    return InlineKeyboardMarkup(rows)


async def cmd_cover(update: Update, context: ContextTypes.DEFAULT_TYPE, *, deny) -> None:
    if await deny(update):
        return
    set_cover_mode(context, True)
    await update.effective_message.reply_text(
        "<b>Cover mode ON</b>\n\n"
        "Forward or send photo/video/text here. I echo a <b>clean copy</b> "
        "(no “Forwarded from”).\n\n"
        "• /compose — back to album workshop\n"
        "• After echo: <b>Send covered → channel</b> if a destination is selected in the menu",
        parse_mode=ParseMode.HTML,
        reply_markup=cover_keyboard(has_channel=False),
    )


async def cmd_compose(update: Update, context: ContextTypes.DEFAULT_TYPE, *, deny) -> None:
    if await deny(update):
        return
    set_cover_mode(context, False)
    await update.effective_message.reply_text(
        "Compose mode ON — album workshop as usual. /cover for anonymous echo.",
    )


async def echo_cover_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    to_chat_id: int | None = None,
) -> int | None:
    """Copy the inbound message without forward header. Returns new message_id or None."""
    msg = update.effective_message
    chat = update.effective_chat
    user = update.effective_user
    if not msg or not chat or not user:
        return None
    if getattr(msg, "has_protected_content", False):
        await msg.reply_text("Protected content — Telegram blocks copy.")
        return None
    if not _rate_ok(int(user.id)):
        return None
    dest = int(to_chat_id or chat.id)
    try:
        copied = await context.bot.copy_message(
            chat_id=dest,
            from_chat_id=chat.id,
            message_id=msg.message_id,
        )
    except (BadRequest, Forbidden) as e:
        logger.info("cover copy failed: %s", e)
        await msg.reply_text(f"Cover copy failed: {e}")
        return None
    mid = int(getattr(copied, "message_id", 0) or 0)
    if mid and dest == chat.id:
        context.chat_data[COVER_LAST_MSG_KEY] = mid
    return mid or None


async def handle_cover_inbound(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    deny,
    channel_id: int | None,
    channel_name: str,
) -> bool:
    """If cover mode, echo and return True (caller should not stage media)."""
    if not is_cover_mode(context):
        return False
    if await deny(update):
        return True
    msg = update.effective_message
    if not msg:
        return True
    # Ignore pure commands in cover mode except we already handled /cover /compose
    if msg.text and msg.text.startswith("/"):
        return False
    mid = await echo_cover_message(update, context)
    if mid:
        await msg.reply_text(
            f"Covered ✓ <code>{mid}</code>",
            parse_mode=ParseMode.HTML,
            reply_markup=cover_keyboard(has_channel=bool(channel_id)),
        )
        if channel_id:
            # Hint only — explicit button sends to channel
            _ = channel_name
    return True


async def send_last_cover_to_channel(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    channel_id: int,
    channel_name: str,
) -> None:
    """Re-copy the last covered echo from DM into the selected channel."""
    q = update.callback_query
    chat = update.effective_chat
    last = context.chat_data.get(COVER_LAST_MSG_KEY)
    if not chat or not last or not channel_id:
        if q:
            await q.answer("No covered message or channel selected", show_alert=True)
        return
    try:
        await context.bot.copy_message(
            chat_id=int(channel_id),
            from_chat_id=chat.id,
            message_id=int(last),
        )
    except (BadRequest, Forbidden) as e:
        if q:
            await q.answer(str(e)[:180], show_alert=True)
        return
    label = (channel_name or "").strip() or str(channel_id)
    if q:
        await q.answer("Sent")
        await q.message.reply_text(f"Covered copy sent → {label}")


def cover_help_blurb() -> str:
    return (
        "<b>Cover mode</b> (/cover) — forward media here for a clean copy "
        "(no Forwarded-from). /compose returns to the album workshop."
    )
