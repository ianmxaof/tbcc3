"""Single-anchor menu UX for the payment bot — edit-in-place instead of reply spam."""

from __future__ import annotations

import logging
from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Message
from telegram.error import BadRequest
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

PAY_UI_ANCHOR_KEY = "pay_ui_anchor"
PAY_UI_ALBUM_KEY = "pay_ui_album_ids"
MENU_HOME = "menu_home"
BACK_BUTTON = InlineKeyboardButton("◀ Main menu", callback_data=MENU_HOME)


def _ui_store(context: ContextTypes.DEFAULT_TYPE) -> dict[str, Any] | None:
    """DM/group updates use user_data; channel posts only have chat_data."""
    if context.user_data is not None:
        return context.user_data
    if context.chat_data is not None:
        return context.chat_data
    return None


def get_anchor(context: ContextTypes.DEFAULT_TYPE) -> dict[str, Any] | None:
    store = _ui_store(context)
    if store is None:
        return None
    raw = store.get(PAY_UI_ANCHOR_KEY)
    return raw if isinstance(raw, dict) else None


def set_anchor(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    chat_id: int,
    message_id: int,
    kind: str = "text",
) -> None:
    store = _ui_store(context)
    if store is None:
        logger.debug("payment_ui: no user_data/chat_data — skip anchor chat=%s msg=%s", chat_id, message_id)
        return
    store[PAY_UI_ANCHOR_KEY] = {
        "chat_id": int(chat_id),
        "message_id": int(message_id),
        "kind": kind if kind in ("text", "photo") else "text",
    }


def clear_anchor(context: ContextTypes.DEFAULT_TYPE) -> None:
    store = _ui_store(context)
    if store is None:
        return
    store.pop(PAY_UI_ANCHOR_KEY, None)


def get_album_message_ids(context: ContextTypes.DEFAULT_TYPE, *, chat_id: int) -> list[int]:
    store = _ui_store(context)
    if store is None:
        return []
    raw = store.get(PAY_UI_ALBUM_KEY)
    if not isinstance(raw, dict):
        return []
    if int(raw.get("chat_id") or 0) != int(chat_id):
        return []
    ids = raw.get("message_ids")
    if not isinstance(ids, list):
        return []
    out: list[int] = []
    for x in ids:
        try:
            out.append(int(x))
        except (TypeError, ValueError):
            continue
    return out


def set_album_message_ids(context: ContextTypes.DEFAULT_TYPE, *, chat_id: int, message_ids: list[int]) -> None:
    store = _ui_store(context)
    if store is None:
        return
    store[PAY_UI_ALBUM_KEY] = {
        "chat_id": int(chat_id),
        "message_ids": [int(x) for x in message_ids],
    }


async def clear_preview_album(bot, context: ContextTypes.DEFAULT_TYPE, *, chat_id: int) -> None:
    for mid in get_album_message_ids(context, chat_id=chat_id):
        await _delete_message(bot, chat_id=chat_id, message_id=mid)
    store = _ui_store(context)
    if store is not None:
        store.pop(PAY_UI_ALBUM_KEY, None)


def with_back_row(markup: InlineKeyboardMarkup | None) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if markup and markup.inline_keyboard:
        rows = [list(r) for r in markup.inline_keyboard]
    rows.append([BACK_BUTTON])
    return InlineKeyboardMarkup(rows)


def _is_benign_edit_error(exc: BadRequest) -> bool:
    msg = str(exc).lower()
    return "message is not modified" in msg


async def _edit_text_message(
    bot,
    *,
    chat_id: int,
    message_id: int,
    text: str,
    reply_markup: InlineKeyboardMarkup | None,
    parse_mode: str | None,
    disable_web_page_preview: bool | None,
) -> bool:
    kwargs: dict[str, Any] = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "reply_markup": reply_markup,
    }
    if parse_mode:
        kwargs["parse_mode"] = parse_mode
    if disable_web_page_preview is not None:
        kwargs["disable_web_page_preview"] = disable_web_page_preview
    try:
        await bot.edit_message_text(**kwargs)
        return True
    except BadRequest as e:
        if _is_benign_edit_error(e):
            return True
        logger.debug("payment_ui edit_message_text failed chat=%s msg=%s: %s", chat_id, message_id, e)
        return False


async def _edit_photo_caption(
    bot,
    *,
    chat_id: int,
    message_id: int,
    caption: str,
    reply_markup: InlineKeyboardMarkup | None,
    parse_mode: str | None,
) -> bool:
    kwargs: dict[str, Any] = {
        "chat_id": chat_id,
        "message_id": message_id,
        "caption": caption,
        "reply_markup": reply_markup,
    }
    if parse_mode:
        kwargs["parse_mode"] = parse_mode
    try:
        await bot.edit_message_caption(**kwargs)
        return True
    except BadRequest as e:
        if _is_benign_edit_error(e):
            return True
        logger.debug("payment_ui edit_message_caption failed chat=%s msg=%s: %s", chat_id, message_id, e)
        return False


async def _delete_message(bot, *, chat_id: int, message_id: int) -> None:
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception as e:
        logger.debug("payment_ui delete_message failed chat=%s msg=%s: %s", chat_id, message_id, e)


async def render_payment_ui(
    *,
    bot,
    chat_id: int,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
    parse_mode: str | None = "HTML",
    edit_message: Message | None = None,
    include_back: bool = False,
    disable_web_page_preview: bool | None = None,
    force_fresh: bool = False,
    reply_to_message_id: int | None = None,
) -> Message | None:
    """Edit the anchor menu message when possible; otherwise send a fresh anchor."""
    kb = with_back_row(reply_markup) if include_back else reply_markup

    targets: list[tuple[int, str]] = []
    if not force_fresh:
        if edit_message is not None:
            kind = "photo" if edit_message.photo else "text"
            targets.append((edit_message.message_id, kind))
        else:
            anchor = get_anchor(context)
            if anchor and int(anchor.get("chat_id") or 0) == int(chat_id):
                mid = anchor.get("message_id")
                if mid is not None:
                    targets.append((int(mid), str(anchor.get("kind") or "text")))

    for message_id, kind in targets:
        if kind == "photo":
            if await _edit_photo_caption(
                bot,
                chat_id=chat_id,
                message_id=message_id,
                caption=text,
                reply_markup=kb,
                parse_mode=parse_mode,
            ):
                set_anchor(context, chat_id=chat_id, message_id=message_id, kind="photo")
                return None
            await _delete_message(bot, chat_id=chat_id, message_id=message_id)
            continue
        if await _edit_text_message(
            bot,
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=kb,
            parse_mode=parse_mode,
            disable_web_page_preview=disable_web_page_preview,
        ):
            set_anchor(context, chat_id=chat_id, message_id=message_id, kind="text")
            return None
        clear_anchor(context)

    send_kwargs: dict[str, Any] = {
        "chat_id": chat_id,
        "text": text,
        "reply_markup": kb,
    }
    if parse_mode:
        send_kwargs["parse_mode"] = parse_mode
    if disable_web_page_preview is not None:
        send_kwargs["disable_web_page_preview"] = disable_web_page_preview
    if reply_to_message_id is not None:
        send_kwargs["reply_to_message_id"] = int(reply_to_message_id)
    sent = await bot.send_message(**send_kwargs)
    set_anchor(context, chat_id=chat_id, message_id=sent.message_id, kind="text")
    return sent
