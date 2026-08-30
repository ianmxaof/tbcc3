"""Shared AOF network discovery menus — infinite-scroll UX across payment, loot, and companion bots."""

from __future__ import annotations

import logging
import math
import os
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy.orm import Session
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app.data.aof_network import ADDLIST_RAW, MAINHUB_RAW, MAIN_GROUP_INVITE
from app.services.aof_links_hub_menu_variants import CHANNEL_PIPES, _gate_href, lv_urls
from app.services.aof_social_links import (
    companion_bot_username,
    loot_bot_username,
    payment_bot_username,
)
from app.services.promo_affiliate_rotation import affiliate_outbound_url, list_candidates

logger = logging.getLogger(__name__)

CALLBACK_PREFIX = "aof_net"
BOT_NETWORK_PLACEMENT = "bot_network_menu"
LANES_PER_PAGE = 8

NetworkView = Literal["home", "lanes", "ai", "sponsors"]


@dataclass(frozen=True)
class NetworkCallback:
    view: NetworkView
    lane_page: int = 0


def network_deep_link_url() -> str:
    """Cross-bot URL button — opens network menu via payment bot /start."""
    pay = payment_bot_username()
    return f"https://t.me/{pay}?start=network" if pay else MAINHUB_RAW


def parse_network_start_payload(payload: str) -> bool:
    p = (payload or "").strip().lower()
    return p in ("network", "explore", "explore_aof", "hub", "map")


def parse_network_callback(data: str) -> NetworkCallback | None:
    raw = (data or "").strip()
    if not raw.startswith(f"{CALLBACK_PREFIX}:"):
        return None
    parts = raw.split(":")
    if len(parts) < 2:
        return None
    action = parts[1].strip().lower()
    if action == "home":
        return NetworkCallback(view="home")
    if action == "lanes":
        page = 0
        if len(parts) >= 3:
            try:
                page = max(0, int(parts[2]))
            except ValueError:
                page = 0
        return NetworkCallback(view="lanes", lane_page=page)
    if action == "ai":
        return NetworkCallback(view="ai")
    if action == "sponsors":
        return NetworkCallback(view="sponsors")
    return None


def network_compact_button() -> InlineKeyboardButton:
    return InlineKeyboardButton("🌐 Explore AOF", callback_data=f"{CALLBACK_PREFIX}:home")


def _short_btn(text: str, *, max_len: int = 64) -> str:
    t = " ".join(str(text or "").split())
    if len(t) <= max_len:
        return t
    return t[: max_len - 1].rstrip() + "…"


def _chunk_buttons(buttons: list[InlineKeyboardButton], *, columns: int = 2) -> list[list[InlineKeyboardButton]]:
    if not buttons:
        return []
    cols = max(1, min(columns, 3))
    out: list[list[InlineKeyboardButton]] = []
    for i in range(0, len(buttons), cols):
        out.append(buttons[i : i + cols])
    return out


def _nav_row(*buttons: InlineKeyboardButton) -> list[InlineKeyboardButton]:
    return list(buttons)


def _list_sponsor_candidates(db: Session, *, placement: str, limit: int) -> list[Any]:
    rows = list_candidates(db, placement)[:limit]
    if rows:
        return rows
    if placement == BOT_NETWORK_PLACEMENT:
        for fallback in ("links_hub_sfw", "links_hub"):
            rows = list_candidates(db, fallback)[:limit]
            if rows:
                return rows
    return []


def _official_bot_rows() -> list[list[InlineKeyboardButton]]:
    pay = payment_bot_username()
    loot = loot_bot_username()
    spicy = companion_bot_username()
    row1: list[InlineKeyboardButton] = []
    if loot:
        row1.append(
            InlineKeyboardButton("🎲 Loot God", url=f"https://t.me/{loot}?start=loot_free")
        )
    if pay:
        row1.append(InlineKeyboardButton("⭐ Subscribe", url=f"https://t.me/{pay}?start=subscribe"))
    rows: list[list[InlineKeyboardButton]] = []
    if row1:
        rows.append(row1)
    row2: list[InlineKeyboardButton] = []
    if spicy:
        row2.append(InlineKeyboardButton("🌶 Spicy AI", url=f"https://t.me/{spicy}"))
    row2.append(InlineKeyboardButton("📋 Secretary", url="https://t.me/aof_secretary_bot"))
    rows.append(row2)
    return rows


def _hub_nav_row(lv: dict[str, str]) -> list[InlineKeyboardButton]:
    loot = _gate_href(lv, "loot") or MAIN_GROUP_INVITE
    addlist = _gate_href(lv, "addlist") or ADDLIST_RAW
    return [
        InlineKeyboardButton("🔗 Mainhub", url=MAINHUB_RAW),
        InlineKeyboardButton("📌 Addlist", url=addlist),
        InlineKeyboardButton("🪙 Loot Room", url=loot),
    ]


def network_menu_html(view: NetworkCallback) -> str:
    if view.view == "lanes":
        total = max(1, math.ceil(len(CHANNEL_PIPES) / LANES_PER_PAGE))
        return (
            "<b>📂 AOF content lanes</b>\n"
            f"Page {view.lane_page + 1}/{total} — tap a channel to join.\n\n"
            "<i>Part of the AOF network — more lanes, bots, and partners on the home screen.</i>"
        )
    if view.view == "ai":
        return (
            "<b>🧠 AI partners</b>\n"
            "Undress · generators · revshare tools — supports AOF.\n\n"
            "<i>Tap a partner below or return home for channels and bots.</i>"
        )
    if view.view == "sponsors":
        return (
            "<b>🤝 Sponsors &amp; partners</b>\n"
            "Curated offers — rotation updates from the dashboard.\n\n"
            "<i>Explore channels and official bots from the home screen.</i>"
        )
    return (
        "<b>🌐 Explore AOF</b>\n"
        "Network of channels, bots, and curated partners.\n"
        "Lose interest in one lane? Pick another below.\n\n"
        "<i>Honest promos only — never fake Telegram staff.</i>"
    )


def build_network_keyboard(db: Session, view: NetworkCallback) -> InlineKeyboardMarkup:
    lv = lv_urls(db)
    rows: list[list[InlineKeyboardButton]] = []

    if view.view == "home":
        rows.append(
            [
                InlineKeyboardButton("📂 All channels", callback_data=f"{CALLBACK_PREFIX}:lanes:0"),
                InlineKeyboardButton("🧠 AI partners", callback_data=f"{CALLBACK_PREFIX}:ai"),
            ]
        )
        rows.append(
            [InlineKeyboardButton("🤝 Sponsors", callback_data=f"{CALLBACK_PREFIX}:sponsors")]
        )
        rows.extend(_official_bot_rows())
        rows.append(_hub_nav_row(lv))
        return InlineKeyboardMarkup(rows)

    if view.view == "lanes":
        start = view.lane_page * LANES_PER_PAGE
        chunk = CHANNEL_PIPES[start : start + LANES_PER_PAGE]
        lane_btns: list[InlineKeyboardButton] = []
        for num, key, label in chunk:
            url = _gate_href(lv, key)
            if not url:
                continue
            short = label.split("·")[0].strip() if "·" in label else label
            lane_btns.append(
                InlineKeyboardButton(_short_btn(f"{num} {short}"), url=url)
            )
        rows.extend(_chunk_buttons(lane_btns, columns=2))
        total_pages = max(1, math.ceil(len(CHANNEL_PIPES) / LANES_PER_PAGE))
        nav: list[InlineKeyboardButton] = []
        if view.lane_page > 0:
            nav.append(
                InlineKeyboardButton(
                    "← Prev",
                    callback_data=f"{CALLBACK_PREFIX}:lanes:{view.lane_page - 1}",
                )
            )
        if view.lane_page + 1 < total_pages:
            nav.append(
                InlineKeyboardButton(
                    "Next →",
                    callback_data=f"{CALLBACK_PREFIX}:lanes:{view.lane_page + 1}",
                )
            )
        if nav:
            rows.append(nav)
        rows.append(
            _nav_row(
                InlineKeyboardButton("🏠 Home", callback_data=f"{CALLBACK_PREFIX}:home"),
                InlineKeyboardButton("🔗 Mainhub", url=MAINHUB_RAW),
            )
        )
        return InlineKeyboardMarkup(rows)

    if view.view == "ai":
        ai_rows = list_candidates(db, "links_hub_ai")[:12]
        if not ai_rows:
            ai_rows = list_candidates(db, "links_hub", network_key="ai")[:12]
        ai_btns: list[InlineKeyboardButton] = []
        for i, row in enumerate(ai_rows, start=1):
            url = affiliate_outbound_url(row, db=db, placement="links_hub_ai")
            if not url.startswith(("http://", "https://", "tg://")):
                continue
            label = (row.label or "Partner").strip()
            ai_btns.append(InlineKeyboardButton(_short_btn(f"{i:02d} {label}"), url=url))
        rows.extend(_chunk_buttons(ai_btns, columns=2))
        rows.append(
            [InlineKeyboardButton("🏠 Home", callback_data=f"{CALLBACK_PREFIX}:home")]
        )
        rows.append(_hub_nav_row(lv))
        return InlineKeyboardMarkup(rows)

    # sponsors
    sponsor_rows = _list_sponsor_candidates(db, placement=BOT_NETWORK_PLACEMENT, limit=10)
    sponsor_btns: list[InlineKeyboardButton] = []
    for i, row in enumerate(sponsor_rows, start=1):
        url = affiliate_outbound_url(row, db=db, placement=BOT_NETWORK_PLACEMENT)
        if not url.startswith(("http://", "https://", "tg://")):
            continue
        label = (row.label or "Partner").strip()
        sponsor_btns.append(InlineKeyboardButton(_short_btn(f"{i:02d} {label}"), url=url))
    if sponsor_btns:
        rows.extend(_chunk_buttons(sponsor_btns, columns=2))
    else:
        rows.append(
            [
                InlineKeyboardButton("🔗 Mainhub", url=MAINHUB_RAW),
                InlineKeyboardButton("📌 Addlist", url=_gate_href(lv, "addlist") or ADDLIST_RAW),
            ]
        )
    rows.append(
        [InlineKeyboardButton("🏠 Home", callback_data=f"{CALLBACK_PREFIX}:home")]
    )
    return InlineKeyboardMarkup(rows)


def build_network_reply_markup_dict(db: Session, view: NetworkCallback | None = None) -> dict[str, Any]:
    vc = view or NetworkCallback(view="home")
    return build_network_keyboard(db, vc).to_dict()


def network_exhaustion_keyboard_rows(db: Session) -> list[list[dict[str, str]]]:
    """Extra row for post-purchase / exhaustion markups (URL buttons)."""
    rows: list[list[dict[str, str]]] = []
    url = network_deep_link_url()
    if url:
        rows.append([{"text": "🌐 Explore AOF network", "url": url}])
    loot = loot_bot_username()
    spicy = companion_bot_username()
    row: list[dict[str, str]] = []
    if loot:
        row.append({"text": "🎲 Loot God", "url": f"https://t.me/{loot}?start=loot_free"})
    if spicy:
        row.append({"text": "🌶 Spicy AI", "url": f"https://t.me/{spicy}"})
    if row:
        rows.append(row)
    hub = MAINHUB_RAW
    if hub:
        rows.append([{"text": "🔗 Mainhub", "url": hub}])
    return rows


async def send_network_menu(
    *,
    chat_id: int,
    context: ContextTypes.DEFAULT_TYPE,
    view: NetworkCallback | None = None,
    reply_to_message_id: int | None = None,
) -> None:
    from app.database.session import SessionLocal

    vc = view or NetworkCallback(view="home")
    db = SessionLocal()
    try:
        text = network_menu_html(vc)
        markup = build_network_keyboard(db, vc)
    finally:
        db.close()
    kwargs: dict[str, Any] = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "reply_markup": markup,
        "disable_web_page_preview": True,
    }
    if reply_to_message_id:
        kwargs["reply_to_message_id"] = reply_to_message_id
    await context.bot.send_message(**kwargs)


async def on_network_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.data:
        return
    parsed = parse_network_callback(query.data)
    if not parsed:
        return
    await query.answer()
    from app.database.session import SessionLocal

    db = SessionLocal()
    try:
        text = network_menu_html(parsed)
        markup = build_network_keyboard(db, parsed)
    finally:
        db.close()
    if query.message:
        try:
            await query.message.edit_text(
                text,
                parse_mode="HTML",
                reply_markup=markup,
                disable_web_page_preview=True,
            )
            return
        except Exception as e:
            logger.debug("network menu edit failed, sending new message: %s", e)
    chat_id = query.message.chat_id if query.message else (update.effective_user.id if update.effective_user else None)
    if chat_id:
        await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode="HTML",
            reply_markup=markup,
            disable_web_page_preview=True,
        )
