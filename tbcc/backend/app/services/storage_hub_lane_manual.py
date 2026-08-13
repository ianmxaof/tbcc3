"""Pinned Storage Hub lane operator manual (top of each forum subtopic)."""

from __future__ import annotations

import asyncio
import html
import logging
import os
from typing import Any

from telegram.constants import ParseMode

from app.data.aof_storage_hub_map import (
    AOF_STORAGE_TOPIC_MAP,
    GATEKEEPER_REVIEW_TOPIC_ID,
    GATEKEEPER_REVIEW_TOPIC_TITLE,
    INBOX_TOPIC_ID,
    INBOX_TOPIC_TITLE,
    SENT_CACHE_TOPIC,
)
from app.services.storage_topic_deposit import storage_hub_chat_id_int

logger = logging.getLogger(__name__)

REDIS_PREFIX = "tbcc:storage:lane:manual:msg"


def lane_manual_targets() -> list[dict[str, Any]]:
    """Forum lanes + inbox + Q&A + SENT VAULT (skip inbox shortcut channel)."""
    out: list[dict[str, Any]] = []
    seen: set[int] = set()
    chat_id = storage_hub_chat_id_int()
    for row in AOF_STORAGE_TOPIC_MAP:
        if not row.network_key:
            continue
        tid = int(row.message_thread_id)
        if tid in seen:
            continue
        seen.add(tid)
        out.append(
            {
                "chat_id": chat_id,
                "message_thread_id": tid,
                "topic_title": row.topic_title,
                "network_key": row.network_key,
            }
        )
    if int(INBOX_TOPIC_ID) not in seen:
        out.append(
            {
                "chat_id": chat_id,
                "message_thread_id": int(INBOX_TOPIC_ID),
                "topic_title": INBOX_TOPIC_TITLE,
                "network_key": "inbox",
            }
        )
    qa_tid = int(GATEKEEPER_REVIEW_TOPIC_ID or 1)
    if qa_tid not in seen:
        out.append(
            {
                "chat_id": chat_id,
                "message_thread_id": qa_tid,
                "topic_title": GATEKEEPER_REVIEW_TOPIC_TITLE,
                "network_key": "qa_master",
            }
        )
    vault_tid = int(SENT_CACHE_TOPIC.message_thread_id)
    if vault_tid not in seen:
        out.append(
            {
                "chat_id": chat_id,
                "message_thread_id": vault_tid,
                "topic_title": SENT_CACHE_TOPIC.topic_title,
                "network_key": "",
            }
        )
    return out


def _redis():
    import redis

    url = (os.getenv("REDIS_URL") or "redis://localhost:6379/0").strip()
    return redis.from_url(url, decode_responses=True, socket_connect_timeout=2)


def manual_redis_key(chat_id: int, message_thread_id: int | None) -> str:
    tid = int(message_thread_id or 0)
    return f"{REDIS_PREFIX}:{int(chat_id)}:{tid}"


def get_stored_lane_manual_message_id(chat_id: int, message_thread_id: int | None) -> int | None:
    try:
        raw = _redis().get(manual_redis_key(chat_id, message_thread_id))
        if raw is not None:
            mid = int(raw)
            return mid if mid > 0 else None
    except Exception:
        logger.debug("lane manual msg read failed", exc_info=True)
    return None


def set_stored_lane_manual_message_id(chat_id: int, message_thread_id: int | None, message_id: int) -> None:
    try:
        _redis().set(manual_redis_key(chat_id, message_thread_id), str(int(message_id)))
    except Exception:
        logger.debug("lane manual msg write failed", exc_info=True)


def format_lane_manual_html(
    *,
    topic_title: str,
    network_key: str | None = None,
) -> str:
    """Telegram HTML pin body — matches docs/STORAGE_HUB_PANEL_MANUAL.md §10."""
    title = html.escape((topic_title or "STORAGE").strip())
    nk = (network_key or "").strip().lower()
    if nk == "qa_master":
        fleet = (
            "<b>Fleet control (you are here)</b>\n"
            "Master panel: deposit any lane · auto-pipe ALL · auto-approve · flush buffers.\n"
            "Tap lane emoji buttons to queue deposits · <code>/qapanel</code> refreshes this panel.\n\n"
        )
    elif nk == "inbox":
        fleet = (
            "<b>Inbox lane</b>\n"
            "Use the inbox intake panel + <code>/intake</code> for batch cadence.\n\n"
        )
    elif not nk:
        fleet = (
            "<b>SENT VAULT</b>\n"
            "Permanent archive + composer panel — Loot preview cap lives here too.\n\n"
        )
    else:
        fleet = (
            "<b>Fleet control</b>\n"
            "Open <b>Q&A | APPROVE / DENY | INTAKE</b> or tap <b>🟡 Master panel</b> on the lane panel below.\n\n"
        )

    return (
        "<b>📖 Storage Hub — lane manual</b>\n\n"
        f"<b>Topic:</b> {title}\n"
        f"<b>Lane key:</b> <code>{html.escape(nk or '—')}</code>\n"
        "<b>Bot:</b> @aof remixer (admin only)\n\n"
        "<b>Quick start</b>\n"
        "1. Forward / scrape media into this topic\n"
        "2. Tap <b>📥 Deposit now</b> on the panel below (or <code>/deposit 50 video</code>)\n"
        "3. Wait for “deposit complete” in this thread\n"
        "4. Channel schedulers pull from the pool · Loot preview is capped\n\n"
        "<b>Lane panel (bottom of thread)</b>\n"
        "• <b>− / +</b> — deposit count (50–200)\n"
        "• <b>− type / + type</b> — video / image / both\n"
        "• <b>Auto-pipe</b> — auto-queue on new media (this lane)\n"
        "• <b>Loot preview</b> — capped albums to Loot Room subtopic\n"
        "• <b>Rebundle</b> — pack loose singles into albums here\n\n"
        "<b>Commands</b>\n"
        "<code>/deposit 50 video</code> · <code>/depositstaged</code>\n"
        "<code>/hubpanel</code> · <code>/review</code>\n"
        "<code>/rebundle</code> · <code>/rebundle go</code>\n\n"
        f"{fleet}"
        "<b>Also see</b>\n"
        "• <b>SENT VAULT</b> — permanent archive + composer\n"
        "• <b>AOF INBOX</b> — batch intake (<code>/intake</code>)\n\n"
        "<i>Control panels repost to the bottom after deposits. This pin stays for reference.</i>"
    )


async def _unpin_topic(bot, *, chat_id: int, message_thread_id: int | None) -> None:
    from app.utils.telegram_forum import bot_api_forum_thread_api_kwargs

    unpin_kw: dict[str, Any] = {"chat_id": int(chat_id)}
    forum_api = bot_api_forum_thread_api_kwargs(message_thread_id)
    try:
        if forum_api:
            await bot.unpin_chat_message(**unpin_kw, api_kwargs=forum_api)
        else:
            await bot.unpin_chat_message(**unpin_kw)
    except Exception:
        logger.debug(
            "lane manual topic unpin failed chat=%s thread=%s",
            chat_id,
            message_thread_id,
            exc_info=True,
        )


async def _pin_message(
    bot,
    *,
    chat_id: int,
    message_id: int,
    message_thread_id: int | None,
) -> bool:
    from app.utils.telegram_forum import bot_api_forum_thread_api_kwargs

    await _unpin_topic(bot, chat_id=chat_id, message_thread_id=message_thread_id)
    pin_kw: dict[str, Any] = {
        "chat_id": int(chat_id),
        "message_id": int(message_id),
        "disable_notification": True,
    }
    forum_api = bot_api_forum_thread_api_kwargs(message_thread_id)
    try:
        if forum_api:
            await bot.pin_chat_message(**pin_kw, api_kwargs=forum_api)
        else:
            await bot.pin_chat_message(**pin_kw)
        return True
    except Exception:
        logger.debug(
            "lane manual pin failed chat=%s thread=%s msg=%s",
            chat_id,
            message_thread_id,
            message_id,
            exc_info=True,
        )
        return False


async def _delete_manual_message(
    bot,
    *,
    chat_id: int,
    message_id: int,
    message_thread_id: int | None,
) -> None:
    from app.services.hub_panel_message import delete_panel_message

    await delete_panel_message(
        bot,
        chat_id=int(chat_id),
        message_id=int(message_id),
        message_thread_id=message_thread_id,
    )


async def ensure_lane_manual_pinned(
    bot,
    *,
    chat_id: int,
    message_thread_id: int | None,
    topic_title: str,
    network_key: str | None = None,
    force_new: bool = False,
) -> dict[str, Any]:
    """Post or refresh the operator manual and pin it at the top of the subtopic."""
    from app.utils.telegram_forum import bot_api_forum_thread_id

    cid = int(chat_id)
    text = format_lane_manual_html(topic_title=topic_title, network_key=network_key)
    stored_mid = get_stored_lane_manual_message_id(cid, message_thread_id)

    send_kw: dict[str, Any] = {
        "chat_id": cid,
        "text": text,
        "parse_mode": ParseMode.HTML,
        "disable_web_page_preview": True,
    }
    api_thread = bot_api_forum_thread_id(message_thread_id)
    if api_thread:
        send_kw["message_thread_id"] = api_thread

    if stored_mid and not force_new:
        try:
            await bot.edit_message_text(message_id=int(stored_mid), **send_kw)
            pinned = await _pin_message(
                bot,
                chat_id=cid,
                message_id=int(stored_mid),
                message_thread_id=message_thread_id,
            )
            return {
                "ok": True,
                "action": "edited",
                "message_id": int(stored_mid),
                "pinned": pinned,
                "panel": "lane_manual",
            }
        except Exception:
            logger.debug(
                "lane manual edit failed chat=%s thread=%s msg=%s",
                cid,
                message_thread_id,
                stored_mid,
                exc_info=True,
            )
            await _delete_manual_message(
                bot,
                chat_id=cid,
                message_id=int(stored_mid),
                message_thread_id=message_thread_id,
            )
            set_stored_lane_manual_message_id(cid, message_thread_id, 0)

    msg = await bot.send_message(**send_kw)
    mid = int(msg.message_id)
    set_stored_lane_manual_message_id(cid, message_thread_id, mid)
    pinned = await _pin_message(
        bot,
        chat_id=cid,
        message_id=mid,
        message_thread_id=message_thread_id,
    )
    return {
        "ok": True,
        "action": "posted",
        "message_id": mid,
        "pinned": pinned,
        "panel": "lane_manual",
    }


async def ensure_all_lane_manuals_pinned(
    bot,
    *,
    force_new: bool = False,
    pause_s: float | None = None,
) -> dict[str, Any]:
    if pause_s is None:
        pause_s = float(os.getenv("TBCC_STORAGE_HUB_PANEL_BOOTSTRAP_PAUSE_S") or "2.5")
    results: list[dict[str, Any]] = []
    errors = 0
    targets = lane_manual_targets()
    for i, target in enumerate(targets):
        if i > 0 and pause_s > 0:
            await asyncio.sleep(pause_s)
        try:
            out = await ensure_lane_manual_pinned(
                bot,
                chat_id=int(target["chat_id"]),
                message_thread_id=target.get("message_thread_id"),
                topic_title=str(target.get("topic_title") or ""),
                network_key=target.get("network_key"),
                force_new=force_new,
            )
            results.append({**target, **out})
            if not out.get("pinned"):
                logger.warning(
                    "lane manual posted but pin failed topic=%s msg=%s",
                    target.get("topic_title"),
                    out.get("message_id"),
                )
        except Exception as e:
            from telegram.error import RetryAfter

            if isinstance(e, RetryAfter):
                wait_s = float(e.retry_after) + 1.0
                logger.warning(
                    "lane manual flood wait %.0fs topic=%s",
                    wait_s,
                    target.get("topic_title"),
                )
                await asyncio.sleep(wait_s)
                try:
                    out = await ensure_lane_manual_pinned(
                        bot,
                        chat_id=int(target["chat_id"]),
                        message_thread_id=target.get("message_thread_id"),
                        topic_title=str(target.get("topic_title") or ""),
                        network_key=target.get("network_key"),
                        force_new=force_new,
                    )
                    results.append({**target, **out})
                    continue
                except Exception as e2:
                    e = e2
            errors += 1
            logger.warning(
                "lane manual pin failed topic=%s: %s",
                target.get("topic_title"),
                e,
                exc_info=True,
            )
            results.append({**target, "ok": False, "error": str(e)[:200]})
    posted = sum(1 for r in results if r.get("action") == "posted")
    edited = sum(1 for r in results if r.get("action") == "edited")
    pinned = sum(1 for r in results if r.get("pinned"))
    return {
        "ok": errors == 0,
        "posted": posted,
        "edited": edited,
        "pinned": pinned,
        "errors": errors,
        "lanes": len(results),
        "results": results,
    }
