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

from app.data.aof_library_forum_topic_map import AOF_LIBRARY_FORUM_TOPIC_MAP
from app.data.aof_storage_hub_map import category_emoji_for_network_key

logger = logging.getLogger(__name__)

_API_BASE = os.getenv("TBCC_API_URL", "http://localhost:8000").rstrip("/")
_FIND_TIMEOUT = httpx.Timeout(connect=15.0, read=300.0, write=30.0, pool=5.0)

# webcams has no product SKU (aof_library_forum_topic_map.py) — a lane button for
# it would always 404 on pool lookup, so it's excluded from the picker.
_MENU_EXCLUDE_LANES = frozenset({"webcams"})
_LANE_LABELS: dict[str, str] = {
    "ai": "AI",
    "ass": "Ass",
    "voyeur": "Voyeur",
    "bop": "BOP",
    "abg": "ABG",
    "big_tits": "Big Tits",
    "milf": "MILF",
    "taboo": "Taboo",
    "full_length": "Full Length",
    "blowjob": "Blowjob",
    "packs": "Packs",
    "goon": "Goon",
}
_PENDING_LANE_KEY = "aof_find_pending_lane"


def _lane_catalog() -> list[str]:
    return [
        row.network_key
        for row in AOF_LIBRARY_FORUM_TOPIC_MAP
        if row.network_key not in _MENU_EXCLUDE_LANES
    ]


def lane_menu_keyboard() -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for key in _lane_catalog():
        emoji = category_emoji_for_network_key(key)
        label = _LANE_LABELS.get(key, key.replace("_", " ").title())
        row.append(InlineKeyboardButton(f"{emoji} {label}", callback_data=f"find:lane:{key}"))
        if len(row) >= 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(rows)


def _lane_picked_keyboard(lane_key: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🎲 Browse this lane", callback_data=f"find:browse:{lane_key}")],
            [InlineKeyboardButton("◀️ Back to lanes", callback_data="find:menu")],
        ]
    )


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
    session_token: str | None = None,
) -> dict:
    url = f"{_API_BASE}/aof-search/find"
    body = {
        "telegram_user_id": int(telegram_user_id),
        "query": query,
        "surface": surface,
        "session_token": session_token,
    }
    with httpx.Client(timeout=_FIND_TIMEOUT) as client:
        r = client.post(url, json=body, headers=_internal_headers())
    if r.status_code == 403:
        return {"ok": False, "forbidden": True, "detail": r.json()}
    r.raise_for_status()
    return r.json()


def _more_keyboard(session_token: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("🔍 Still want more?", callback_data=f"find:more:{session_token}")]]
    )


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
    override_query: str | None = None,
    override_surface: str | None = None,
) -> None:
    user = update.effective_user
    if not user:
        return
    msg = update.effective_message
    if not msg:
        return

    if override_query is not None:
        query = override_query.strip()
        surface_arg = override_surface
        if surface_arg is None:
            surface_arg = _default_surface(bot_kind)
    else:
        text = (msg.text or msg.caption or "").strip()
        parts = text.split(maxsplit=1)
        query = parts[1].strip() if len(parts) > 1 else ""
        if not query:
            await msg.reply_html(
                _find_help_html(bot_kind=bot_kind),
                reply_markup=lane_menu_keyboard(),
                disable_web_page_preview=True,
            )
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
            f"<i>{html.escape(str(reason))}</i>\n\n"
            f"Try the web archive instead:\n<code>/macrosearch {html.escape(query[:80])}</code>",
            parse_mode="HTML",
        )
        return

    sent = int((result.get("delivery") or {}).get("media_sent") or 0)
    res = result.get("result") or {}
    emoji = res.get("primary_emoji") or "🔍"
    remaining = (result.get("access") or {}).get("searches_remaining")
    rem_note = f" · {remaining} searches left today" if remaining is not None else ""
    note = ""
    if res.get("loosened"):
        note = "\n<i>Widened the match — exact tags ran out.</i>"
    elif res.get("vault_pulled"):
        note = "\n<i>Pulled a few fresh ones from the vault.</i>"
    await status.edit_text(
        f"<b>{emoji} Sent {sent} item(s) to your DM</b>{html.escape(rem_note)}{note}",
        parse_mode="HTML",
        disable_web_page_preview=True,
    )

    session_token = result.get("session_token")
    if result.get("has_more") and session_token:
        try:
            await msg.reply_html(
                "Still want more?",
                reply_markup=_more_keyboard(session_token),
                disable_web_page_preview=True,
            )
        except TelegramError:
            pass


async def on_find_more_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query_cb = update.callback_query
    if not query_cb or not query_cb.data:
        return
    user = update.effective_user
    if not user:
        return
    token = query_cb.data.split(":", 2)[-1]
    await query_cb.answer("Searching…")

    try:
        import asyncio

        result = await asyncio.to_thread(
            _post_find,
            telegram_user_id=int(user.id),
            query="",
            surface=None,
            session_token=token,
        )
    except httpx.HTTPStatusError as e:
        detail = ""
        try:
            detail = str(e.response.json())
        except Exception:
            detail = (e.response.text or str(e))[:300] if e.response else str(e)
        await query_cb.message.reply_html(f"<b>Search failed</b>\n<code>{html.escape(detail)}</code>")
        return
    except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.ConnectError):
        await query_cb.message.reply_html("<b>TBCC is catching up</b>\nTap again in a few seconds.")
        return

    if result.get("forbidden") or not result.get("ok"):
        detail = result.get("detail") or {}
        message = detail.get("message") or result.get("reason") or "No more matches."
        try:
            await query_cb.edit_message_text(f"<i>{html.escape(str(message))}</i>", parse_mode="HTML")
        except TelegramError:
            pass
        return

    sent = int((result.get("delivery") or {}).get("media_sent") or 0)
    res = result.get("result") or {}
    emoji = res.get("primary_emoji") or "🔍"
    note = ""
    if res.get("loosened"):
        note = "\n<i>Widened the match — exact tags ran out.</i>"
    elif res.get("vault_pulled"):
        note = "\n<i>Pulled a few fresh ones from the vault.</i>"

    new_token = result.get("session_token") or token
    kb = _more_keyboard(new_token) if result.get("has_more") else None
    try:
        await query_cb.edit_message_text(
            f"<b>{emoji} Sent {sent} more item(s) to your DM</b>{note}",
            parse_mode="HTML",
            reply_markup=kb,
        )
    except TelegramError:
        pass


async def cmd_searchmenu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/searchmenu — post the lane picker as a fresh message (not an edit)."""
    msg = update.effective_message
    if not msg:
        return
    context.user_data.pop(_PENDING_LANE_KEY, None)
    await msg.reply_html(
        "<b>🔍 Search the AOF Archive</b>\nPick a lane, or run <code>/find keywords</code> directly.",
        reply_markup=lane_menu_keyboard(),
        disable_web_page_preview=True,
    )


async def on_find_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """◀️ Back to lanes — redraw the top-level picker in place."""
    query_cb = update.callback_query
    if not query_cb:
        return
    context.user_data.pop(_PENDING_LANE_KEY, None)
    await query_cb.answer()
    try:
        await query_cb.edit_message_text(
            "<b>🔍 Search the AOF Archive</b>\nPick a lane, or run <code>/find keywords</code> directly.",
            parse_mode="HTML",
            reply_markup=lane_menu_keyboard(),
        )
    except TelegramError:
        pass


async def on_find_lane_pick_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """A lane button was tapped — remember it and ask for the query text."""
    query_cb = update.callback_query
    if not query_cb or not query_cb.data:
        return
    lane_key = query_cb.data.split(":", 2)[-1]
    context.user_data[_PENDING_LANE_KEY] = lane_key
    await query_cb.answer()
    emoji = category_emoji_for_network_key(lane_key)
    label = _LANE_LABELS.get(lane_key, lane_key.replace("_", " ").title())
    try:
        await query_cb.edit_message_text(
            f"<b>{emoji} {html.escape(label)}</b>\n"
            "Send a few keywords to narrow it down, or just browse.",
            parse_mode="HTML",
            reply_markup=_lane_picked_keyboard(lane_key),
        )
    except TelegramError:
        pass


async def on_find_browse_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """🎲 Browse this lane — search on the lane emoji alone, no typed keywords."""
    query_cb = update.callback_query
    if not query_cb or not query_cb.data:
        return
    lane_key = query_cb.data.split(":", 2)[-1]
    context.user_data.pop(_PENDING_LANE_KEY, None)
    await query_cb.answer("Searching…")
    emoji = category_emoji_for_network_key(lane_key)
    bot_kind = str(context.bot_data.get("aof_find_bot_kind") or "loot")
    await cmd_find(update, context, bot_kind=bot_kind, override_query=emoji)


async def consume_find_pending_lane_text(
    update: Update, context: ContextTypes.DEFAULT_TYPE, *, bot_kind: str
) -> bool:
    """Call from a bot's own free-text handler. True = this text was the lane
    query and has been dispatched to search; caller should stop processing it
    as anything else. False = no lane was pending, caller's normal flow applies.
    """
    lane_key = (context.user_data or {}).pop(_PENDING_LANE_KEY, None)
    if not lane_key:
        return False
    msg = update.effective_message
    text = (msg.text if msg else "") or ""
    emoji = category_emoji_for_network_key(lane_key)
    await cmd_find(update, context, bot_kind=bot_kind, override_query=f"{emoji} {text}".strip())
    return True


def build_find_handlers(*, bot_kind: str = "loot"):
    from telegram.ext import CallbackQueryHandler, CommandHandler

    async def _cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
        context.bot_data["aof_find_bot_kind"] = bot_kind
        await cmd_find(update, context, bot_kind=bot_kind)

    async def _lane_pick(update: Update, context: ContextTypes.DEFAULT_TYPE):
        context.bot_data["aof_find_bot_kind"] = bot_kind
        await on_find_lane_pick_callback(update, context)

    async def _browse(update: Update, context: ContextTypes.DEFAULT_TYPE):
        context.bot_data["aof_find_bot_kind"] = bot_kind
        await on_find_browse_callback(update, context)

    return [
        CommandHandler("find", _cmd),
        CommandHandler("searchmenu", cmd_searchmenu),
        CallbackQueryHandler(on_find_more_callback, pattern=r"^find:more:"),
        CallbackQueryHandler(_lane_pick, pattern=r"^find:lane:"),
        CallbackQueryHandler(_browse, pattern=r"^find:browse:"),
        CallbackQueryHandler(on_find_menu_callback, pattern=r"^find:menu$"),
    ]
