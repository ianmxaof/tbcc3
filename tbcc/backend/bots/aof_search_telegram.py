"""Telegram /find handlers — keyword search across AOF surfaces."""

from __future__ import annotations

import html
import logging
import os
import time

import httpx
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction
from telegram.error import TelegramError
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

_API_BASE = os.getenv("TBCC_API_URL", "http://localhost:8000").rstrip("/")
_FIND_TIMEOUT = httpx.Timeout(connect=15.0, read=300.0, write=30.0, pool=5.0)


def _internal_headers() -> dict[str, str]:
    key = (os.getenv("TBCC_INTERNAL_API_KEY") or "").strip()
    if key:
        return {"X-TBCC-Internal-Key": key}
    return {}


def _default_surface(bot_kind: str) -> str:
    if bot_kind == "payment":
        return "library"
    if bot_kind == "macro":
        return "vip"  # macro bot picks best via API; this is help-text default
    return "loot_room"


def _post_find(
    *,
    telegram_user_id: int,
    query: str,
    surface: str | None,
) -> dict:
    url = f"{_API_BASE}/aof-search/find"
    body = {
        "telegram_user_id": int(telegram_user_id),
        "query": query,
        "surface": surface,
    }
    with httpx.Client(timeout=_FIND_TIMEOUT) as client:
        r = client.post(url, json=body, headers=_internal_headers())
    if r.status_code == 403:
        return {"ok": False, "forbidden": True, "detail": r.json()}
    r.raise_for_status()
    return r.json()


def _find_help_html(*, bot_kind: str) -> str:
    surface = _default_surface(bot_kind)
    return (
        "<b>🔍 AOF Search</b>\n"
        "Type keywords, lane tags, or emoji — results DM as an album.\n\n"
        "<b>Examples</b>\n"
        "• <code>/find milf office</code>\n"
        "• <code>/find pawg thick</code>\n"
        "• <code>/find 🍒 busty</code>\n"
        "• <code>/find #goon</code>\n\n"
        f"Default surface: <code>{html.escape(surface)}</code>\n"
        "Loot key → library · VIP → all lanes + VIP pool"
    )


async def cmd_find(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    bot_kind: str = "loot",
) -> None:
    user = update.effective_user
    if not user:
        return
    msg = update.effective_message
    if not msg:
        return

    text = (msg.text or msg.caption or "").strip()
    parts = text.split(maxsplit=1)
    query = parts[1].strip() if len(parts) > 1 else ""
    if not query:
        await msg.reply_html(_find_help_html(bot_kind=bot_kind), disable_web_page_preview=True)
        return

    surface_arg = None
    if query.lower().startswith("vip:"):
        surface_arg = "vip"
        query = query[4:].strip()
    elif query.lower().startswith("library:"):
        surface_arg = "library"
        query = query[8:].strip()
    elif query.lower().startswith("loot:"):
        surface_arg = "loot_room"
        query = query[5:].strip()
    if not query:
        await msg.reply_html("Add keywords after the surface prefix.", disable_web_page_preview=True)
        return

    if surface_arg is None:
        surface_arg = _default_surface(bot_kind)

    try:
        await context.bot.send_chat_action(chat_id=msg.chat_id, action=ChatAction.UPLOAD_PHOTO)
    except TelegramError:
        pass

    status = await msg.reply_html("<i>Searching the archive…</i>", disable_web_page_preview=True)
    try:
        import asyncio

        result = await asyncio.to_thread(
            _post_find,
            telegram_user_id=int(user.id),
            query=query,
            surface=surface_arg,
        )
    except httpx.HTTPStatusError as e:
        detail = ""
        try:
            detail = str(e.response.json())
        except Exception:
            detail = (e.response.text or str(e))[:300] if e.response else str(e)
        await status.edit_text(f"<b>Search failed</b>\n<code>{html.escape(detail)}</code>", parse_mode="HTML")
        return
    except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.ConnectError) as e:
        await status.edit_text(
            "<b>TBCC is catching up</b>\nTry <code>/find</code> again in a few seconds.",
            parse_mode="HTML",
        )
        logger.warning("aof find transient error: %s", e)
        return

    if result.get("forbidden"):
        detail = result.get("detail") or {}
        message = detail.get("message") or detail.get("detail") or "Search not allowed."
        pay = (os.getenv("TBCC_PAYMENT_BOT_USERNAME") or "aofsubscriptions_bot").strip().lstrip("@")
        rows = [
            [InlineKeyboardButton("🗝 Loot key", url=f"https://t.me/{pay}?start=loot")],
            [InlineKeyboardButton("⭐ AOF VIP", url=f"https://t.me/{pay}?start=subscribe")],
        ]
        await status.edit_text(
            f"<b>{html.escape(str(message))}</b>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(rows),
        )
        return

    if not result.get("ok"):
        reason = result.get("reason") or "no_matches"
        await status.edit_text(
            f"<b>No matches</b> for <code>{html.escape(query[:80])}</code>\n"
            f"<i>{html.escape(str(reason))}</i>",
            parse_mode="HTML",
        )
        return

    sent = int((result.get("delivery") or {}).get("media_sent") or 0)
    res = result.get("result") or {}
    emoji = res.get("primary_emoji") or "🔍"
    remaining = (result.get("access") or {}).get("searches_remaining")
    rem_note = f" · {remaining} searches left today" if remaining is not None else ""
    await status.edit_text(
        f"<b>{emoji} Sent {sent} item(s) to your DM</b>{html.escape(rem_note)}",
        parse_mode="HTML",
        disable_web_page_preview=True,
    )


def build_find_handlers(*, bot_kind: str = "loot"):
    from telegram.ext import CommandHandler

    async def _cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await cmd_find(update, context, bot_kind=bot_kind)

    return [CommandHandler("find", _cmd)]
