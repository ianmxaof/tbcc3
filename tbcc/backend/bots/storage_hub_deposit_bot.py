"""Bot API /deposit handler for Storage Hub forum topics (Album Composer or Secretary)."""

from __future__ import annotations

import logging
import os

from telegram import Update
from telegram.ext import ContextTypes

from app.database.session import SessionLocal
from app.services.storage_topic_deposit import (
    default_deposit_media_types,
    format_deposit_error_text,
    format_deposit_progress_text,
    parse_deposit_command,
    queue_storage_topic_deposit,
    queue_storage_topic_deposit_staged,
    resolve_deposit_limit,
    run_deposit_subtopic_followup,
    storage_hub_chat_id_int,
)
from app.services.tbcc_telegram_admin import (
    GROUP_ANONYMOUS_BOT_ID,
    can_operate_storage_hub_bot_api,
)

logger = logging.getLogger(__name__)


def secretary_storage_deposit_enabled() -> bool:
    return (os.getenv("TBCC_SECRETARY_STORAGE_DEPOSIT") or "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def album_composer_storage_deposit_enabled() -> bool:
    return (os.getenv("TBCC_ALBUM_COMPOSER_STORAGE_DEPOSIT") or "1").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _deposit_disabled_message(bot_label: str) -> str:
    if bot_label == "album-composer":
        return "Storage /deposit is disabled on Album Composer (TBCC_ALBUM_COMPOSER_STORAGE_DEPOSIT)."
    return "Storage /deposit is disabled on secretary bot (TBCC_SECRETARY_STORAGE_DEPOSIT)."


async def cmd_deposit(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    bot_label: str = "album-composer",
) -> None:
    """Queue N newest deduped items from the current Storage Hub subtopic."""
    if bot_label == "album-composer":
        if not album_composer_storage_deposit_enabled():
            msg = update.effective_message
            if msg:
                await msg.reply_text(_deposit_disabled_message(bot_label))
            return
    elif not secretary_storage_deposit_enabled():
        msg = update.effective_message
        if msg:
            await msg.reply_text(_deposit_disabled_message(bot_label))
        return

    msg = update.effective_message
    if not msg:
        return
    if not can_operate_storage_hub_bot_api(update):
        await _reply_deposit_denied(update, msg)
        return

    chat = update.effective_chat
    if not chat or int(chat.id) != storage_hub_chat_id_int():
        await msg.reply_text("❌ /deposit only works inside Storage & Bot Hangar forum subtopics.")
        return

    thread_id = getattr(msg, "message_thread_id", None)
    if not thread_id:
        await msg.reply_text("❌ Post /deposit inside a forum subtopic (not General).")
        return

    parsed = parse_deposit_command(msg.text or msg.caption or "")
    if parsed is None:
        await msg.reply_text(
            "Usage: /deposit N — N can be 1–200 (e.g. /deposit 5 or /deposit 15).\n"
            "Optional filter: videos (default), photos, or both.\n"
            "Example: /deposit 5 both"
        )
        return

    limit_raw, media_override = parsed
    limit = resolve_deposit_limit(limit_raw)
    media_types = media_override or default_deposit_media_types()

    await _run_deposit_job(
        update,
        context,
        message_thread_id=int(thread_id),
        limit=limit,
        media_types=media_types,
    )


async def cmd_deposit_staged(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    message_ids: list[int],
    message_thread_id: int,
    bot_label: str = "album-composer",
) -> None:
    """Deposit exactly the staged message ids from the current workshop session."""
    if bot_label == "album-composer" and not album_composer_storage_deposit_enabled():
        msg = update.effective_message
        if msg:
            await msg.reply_text(_deposit_disabled_message(bot_label))
        return
    if not can_operate_storage_hub_bot_api(update):
        msg = update.effective_message
        if msg:
            await _reply_deposit_denied(update, msg)
        return

    chat = update.effective_chat
    if not chat or int(chat.id) != storage_hub_chat_id_int():
        return

    ids = [int(x) for x in message_ids if int(x) > 0]
    if not ids:
        msg = update.effective_message
        if msg:
            await msg.reply_text("Stage media in this topic first, then tap Deposit staged.")
        return

    await _run_deposit_job(
        update,
        context,
        message_thread_id=int(message_thread_id),
        limit=len(ids),
        media_types=default_deposit_media_types(),
        staged_message_ids=ids,
    )


async def _run_deposit_job(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    message_thread_id: int,
    limit: int,
    media_types: str,
    staged_message_ids: list[int] | None = None,
    reply_msg=None,
) -> None:
    msg = reply_msg or update.effective_message
    chat = update.effective_chat
    if not msg or not chat:
        return

    db = SessionLocal()
    try:
        if staged_message_ids:
            report = queue_storage_topic_deposit_staged(
                db,
                message_thread_id=message_thread_id,
                message_ids=staged_message_ids,
                media_types=media_types,
            )
        else:
            report = queue_storage_topic_deposit(
                db,
                message_thread_id=message_thread_id,
                limit=limit,
                media_types=media_types,
            )
    finally:
        db.close()

    if not report.get("ok"):
        await msg.reply_text(format_deposit_error_text(report))
        return

    job_id = str(report.get("job_id") or report.get("id") or "")
    progress = await msg.reply_text(format_deposit_progress_text(report, html=False, markdown=False))

    async def _edit_progress(text: str) -> None:
        try:
            await context.bot.edit_message_text(
                chat_id=chat.id,
                message_id=progress.message_id,
                text=text,
            )
        except Exception:
            logger.debug("deposit progress edit failed", exc_info=True)

    context.application.create_task(
        run_deposit_subtopic_followup(
            report,
            job_id=job_id,
            limit=limit,
            html=False,
            markdown=False,
            set_message_text=_edit_progress,
        )
    )


async def _reply_deposit_denied(update: Update, msg) -> None:
    user = update.effective_user
    lines = [
        "Admin only — /deposit requires your Telegram user id in "
        "ADMIN_TELEGRAM_ID or TBCC_ALBUM_COMPOSER_EXTRA_ADMIN_IDS (tbcc/.env).",
    ]
    if user:
        lines.append(f"Telegram saw sender user id: {user.id}")
        if int(user.id) == GROUP_ANONYMOUS_BOT_ID:
            lines.append(
                "Anonymous / post-as-group is supported in Storage Hub when "
                "TBCC_STORAGE_HUB_ALLOW_CHANNEL_POST=1 (default)."
            )
    sender_chat = getattr(msg, "sender_chat", None)
    if sender_chat:
        label = sender_chat.title or sender_chat.username or str(sender_chat.id)
        lines.append(f"Sender chat: «{label}» (id {sender_chat.id})")
    lines.append("Restart TBCC-AlbumComposer after .env changes, then retry.")
    await msg.reply_text("\n".join(lines))
