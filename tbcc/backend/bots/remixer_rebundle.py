"""Remixer rebundle — group loose media into albums in any chat the bot admins."""

from __future__ import annotations

import logging
from typing import Awaitable, Callable

from telegram import ChatMember, Update
from telegram.constants import ChatMemberStatus, ParseMode
from telegram.ext import ContextTypes

from app.services.tbcc_telegram_admin import GROUP_ANONYMOUS_BOT_ID

logger = logging.getLogger(__name__)

DenyFn = Callable[[Update], Awaitable[bool]]


def rebundle_help_blurb() -> str:
    return (
        "<b>/rebundle</b> — preview loose media → albums in this chat/topic\n"
        "<b>/rebundle go</b> — post full + partial albums, then delete source singles"
    )


def _actor_user_id(update: Update) -> int | None:
    user = update.effective_user
    if user and user.id:
        return int(user.id)
    msg = update.effective_message
    if msg and msg.from_user and msg.from_user.id:
        return int(msg.from_user.id)
    return None


def _anonymous_group_operator(update: Update) -> bool:
    """True when posting as group / anonymous admin (Telegram Group Anonymous Bot)."""
    chat = update.effective_chat
    if not chat or chat.type not in ("group", "supergroup"):
        return False
    uid = _actor_user_id(update)
    if uid is not None and int(uid) == GROUP_ANONYMOUS_BOT_ID:
        return True
    msg = update.effective_message
    sender = getattr(msg, "sender_chat", None) if msg else None
    if sender and int(getattr(sender, "id", 0) or 0) == int(chat.id):
        return True
    return False


async def deny_rebundle_unauthorized(update: Update) -> bool:
    """
    Allow TBCC operator ids, or anonymous/group-as-sender in groups.
    Silent deny in groups for everyone else (no spam).
    """
    from bots.album_composer_bot import _admin_ids, _authorized

    if _authorized(_actor_user_id(update)):
        return False
    if _anonymous_group_operator(update) and _admin_ids():
        # Group admins can only post anonymously when they are admins; bot still
        # requires configured operator ids so empty .env never opens the gate.
        return False
    chat = update.effective_chat
    if chat and chat.type in ("group", "supergroup", "channel"):
        return True
    msg = update.effective_message
    if msg:
        await msg.reply_text(
            "Admin only — set ADMIN_TELEGRAM_ID in tbcc/.env, or post as yourself "
            "(not anonymously) in a group where you are operator."
        )
    return True


async def _bot_is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    chat = update.effective_chat
    if not chat:
        return False
    try:
        me = await context.bot.get_me()
        member: ChatMember = await context.bot.get_chat_member(chat.id, me.id)
        status = getattr(member, "status", None)
        return status in (
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.OWNER,
            "administrator",
            "creator",
        )
    except Exception as e:
        logger.debug("rebundle bot admin check failed chat=%s: %s", getattr(chat, "id", None), e)
        return False


def _parse_go(args: list[str] | None) -> bool:
    if not args:
        return False
    token = (args[0] or "").strip().lower()
    return token in ("go", "run", "yes", "apply", "post")


async def cmd_rebundle(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    deny: DenyFn | None = None,
) -> None:
    deny_fn = deny or deny_rebundle_unauthorized
    if await deny_fn(update):
        return
    msg = update.effective_message
    chat = update.effective_chat
    if not msg or not chat:
        return

    if chat.type not in ("group", "supergroup"):
        await msg.reply_text(
            "/rebundle only works inside a group or forum topic where this bot is admin."
        )
        return

    if not await _bot_is_admin(update, context):
        await msg.reply_text(
            "Promote this bot to <b>admin</b> in this group first "
            "(needed to see topic media + post albums).",
            parse_mode=ParseMode.HTML,
        )
        return

    do_run = _parse_go(list(context.args or []))
    thread_id = getattr(msg, "message_thread_id", None)
    thread_id_i = int(thread_id) if thread_id else None
    channel_ident = str(int(chat.id))

    if do_run:
        from app.workers.topic_rebundle_worker import rebundle_storage_topic_task

        rebundle_storage_topic_task.delay(
            message_thread_id=thread_id_i,
            channel_ident=channel_ident,
            dry_run=False,
            allow_partial=True,
            delete_sources=True,
        )
        where = f"topic {thread_id_i}" if thread_id_i else "this chat"
        await msg.reply_text(
            f"Queued rebundle for {where} "
            f"(full + partial albums; source singles deleted after post).",
            reply_to_message_id=msg.message_id,
        )
        return

    from app.services.topic_rebundle_service import (
        format_topic_rebundle_summary,
        rebundle_storage_topic_loose_media_sync,
    )

    await msg.chat.send_action("typing")
    try:
        report = rebundle_storage_topic_loose_media_sync(
            message_thread_id=thread_id_i,
            channel_ident=channel_ident,
            dry_run=True,
            allow_partial=True,
            delete_sources=True,
        )
    except Exception as e:
        logger.warning("rebundle preview failed chat=%s: %s", channel_ident, e, exc_info=True)
        await msg.reply_text(
            "Preview failed — is the <b>admin Telethon session</b> a member of this group?\n"
            f"<code>{str(e)[:280]}</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    summary = format_topic_rebundle_summary(report, html=True)
    await msg.reply_text(
        f"{summary}\n\nRun <code>/rebundle go</code> to post + delete sources.",
        parse_mode=ParseMode.HTML,
    )
