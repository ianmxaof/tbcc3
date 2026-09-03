"""Q&A | APPROVE / DENY | INTAKE — master control panel (Storage Hub operator checkpoint)."""

from __future__ import annotations

import html
import logging
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.data.aof_storage_hub_map import (
    CONTENT_LANE_NETWORK_KEYS,
    GATEKEEPER_REVIEW_TOPIC_TITLE,
    category_emoji_for_network_key,
    storage_map_by_key,
)
from app.models.media import Media
from app.services.export_flywheel_service import pool_id_for_network_key
from app.services.gatekeeper_review import (
    count_quarantine_waiting,
    inbox_quarantine_buffer_count,
    review_thread_id,
)
from app.services.hub_intake_policy import auto_pipe_destination_label, hub_master_auto_approve_enabled
from app.services.quarantine_batch_review import lane_quarantine_buffer_count, review_batch_size
from app.services.storage_auto_pipe import (
    all_lanes_auto_pipe_on,
    auto_pipe_debounce_s,
    set_all_lanes_auto_pipe,
    storage_auto_pipe_enabled,
)
from app.services.storage_deposit_control import (
    format_deposit_command,
    get_deposit_limit,
    get_deposit_media_types,
    media_type_label,
)

logger = logging.getLogger(__name__)

REDIS_PANEL_PREFIX = "tbcc:qa:master:panel:msg"
CALLBACK_PREFIX = "qmp:"
LANES_PER_PAGE = 6


def panel_redis_key(chat_id: int, message_thread_id: int | None) -> str:
    from app.utils.telegram_forum import normalize_hub_panel_thread_id

    tid = normalize_hub_panel_thread_id(message_thread_id)
    return f"{REDIS_PANEL_PREFIX}:{int(chat_id)}:{tid}"


def get_stored_panel_message_id(chat_id: int, message_thread_id: int | None) -> int | None:
    try:
        import redis

        url = (__import__("os").getenv("REDIS_URL") or "redis://localhost:6379/0").strip()
        r = redis.from_url(url, decode_responses=True, socket_connect_timeout=2)
        raw = r.get(panel_redis_key(chat_id, message_thread_id))
        if raw is not None:
            mid = int(raw)
            return mid if mid > 0 else None
    except Exception:
        logger.debug("qa master panel msg read failed", exc_info=True)
    return None


def set_stored_panel_message_id(chat_id: int, message_thread_id: int | None, message_id: int) -> None:
    try:
        import redis

        url = (__import__("os").getenv("REDIS_URL") or "redis://localhost:6379/0").strip()
        r = redis.from_url(url, decode_responses=True, socket_connect_timeout=2)
        r.set(panel_redis_key(chat_id, message_thread_id), str(int(message_id)))
    except Exception:
        logger.debug("qa master panel msg write failed", exc_info=True)


def _pool_counts(db: Session, pool_id: int | None) -> tuple[int, int, int]:
    if not pool_id:
        return 0, 0, 0
    photo_types = ("photo", "gif")
    photos = (
        db.query(func.count(Media.id))
        .filter(
            Media.pool_id == int(pool_id),
            Media.status == "approved",
            Media.media_type.in_(photo_types),
        )
        .scalar()
        or 0
    )
    videos = (
        db.query(func.count(Media.id))
        .filter(
            Media.pool_id == int(pool_id),
            Media.status == "approved",
            Media.media_type == "video",
        )
        .scalar()
        or 0
    )
    quarantine = (
        db.query(func.count(Media.id))
        .filter(Media.pool_id == int(pool_id), Media.status == "quarantine")
        .scalar()
        or 0
    )
    return int(photos), int(videos), int(quarantine)


def lane_inventory_rows(db: Session) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for nk in sorted(CONTENT_LANE_NETWORK_KEYS):
        if nk in ("inbox", "packs"):
            continue
        pid = pool_id_for_network_key(db, nk)
        photos, videos, pool_q = _pool_counts(db, pid)
        waiting = count_quarantine_waiting(db, lane_key=nk)
        buf = lane_quarantine_buffer_count(nk)
        from app.services.storage_auto_pipe import lane_auto_pipe_enabled

        rows.append(
            {
                "network_key": nk,
                "emoji": category_emoji_for_network_key(nk),
                "photos": photos,
                "videos": videos,
                "pool_quarantine": pool_q,
                "waiting": waiting,
                "buffer": buf,
                "auto_pipe": lane_auto_pipe_enabled(nk),
                "thread_id": storage_map_by_key().get(nk).message_thread_id
                if storage_map_by_key().get(nk)
                else None,
            }
        )
    return rows


def _lane_keys_page(page: int) -> list[str]:
    keys = [nk for nk in sorted(CONTENT_LANE_NETWORK_KEYS) if nk not in ("inbox", "packs")]
    start = max(0, int(page)) * LANES_PER_PAGE
    return keys[start : start + LANES_PER_PAGE]


def format_qa_master_panel_html(db: Session, *, page: int = 0) -> str:
    from app.services.gatekeeper_review import format_lane_pool_depth_html
    from app.services.intake_scheduler import format_status_text

    waiting_all = count_quarantine_waiting(db)
    inbox_buf = inbox_quarantine_buffer_count()
    lim = get_deposit_limit()
    mt = media_type_label(get_deposit_media_types())
    lines = [
        f"🟡 <b>{html.escape(GATEKEEPER_REVIEW_TOPIC_TITLE)}</b> · <b>MASTER PANEL</b>",
        f"Topic: <code>{review_thread_id() or '?'}</code>",
        "",
        f"<b>Auto-pipe (all lanes):</b> {'ON' if storage_auto_pipe_enabled() else 'OFF'}"
        f" · lanes {'ALL ON' if all_lanes_auto_pipe_on() else 'mixed'}"
        f" · debounce {auto_pipe_debounce_s()}s",
        f"<b>Auto-approve:</b> {'ON' if hub_master_auto_approve_enabled() else 'OFF'}",
        f"<b>Mode:</b> {html.escape(auto_pipe_destination_label())}",
        f"<b>Q&A waiting:</b> {waiting_all} · batch {review_batch_size()}+1",
        f"<b>Deposit preset:</b> {lim} · <code>{mt}</code> — "
        f"<code>{format_deposit_command(lim, get_deposit_media_types())}</code>",
    ]
    if inbox_buf:
        lines.append(f"<b>Inbox Q&A buffer:</b> {inbox_buf}")
    lines.append("")
    lines.append("<b>Lane inventory</b> <i>(📷 photos · 🎬 videos · 🟡 quarantine · buf)</i>")
    inv = lane_inventory_rows(db)
    page_keys = set(_lane_keys_page(page))
    for row in inv:
        nk = row["network_key"]
        if nk not in page_keys:
            continue
        pipe = "▶" if row["auto_pipe"] else "⏸"
        lines.append(
            f"{row['emoji']} <code>{html.escape(nk)}</code> {pipe} · "
            f"📷{row['photos']} · 🎬{row['videos']} · 🟡{row['waiting']}"
            + (f" · buf {row['buffer']}" if row["buffer"] else "")
        )
    total_pages = max(1, (len(inv) + LANES_PER_PAGE - 1) // LANES_PER_PAGE)
    lines.append(f"<i>Lane page {page + 1}/{total_pages}</i>")
    try:
        lines.append(format_lane_pool_depth_html(db, max_lanes=6))
    except Exception:
        pass
    lines.append("")
    lines.append(format_status_text())
    lines.append(
        "<i>Tap a lane to deposit · global toggles apply to every content lane · "
        "/review for bulk approve.</i>"
    )
    return "\n".join(lines)


def qa_master_panel_keyboard(*, page: int = 0) -> Any:
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    from app.services.admin_bridge import dashboard_public_base

    lim = get_deposit_limit()
    dash_url = dashboard_public_base()
    rows: list[list[Any]] = [
        [
            InlineKeyboardButton("🔄 Refresh", callback_data=f"{CALLBACK_PREFIX}refresh:{page}"),
            InlineKeyboardButton("📋 Review", callback_data=f"{CALLBACK_PREFIX}review"),
        ],
        [
            InlineKeyboardButton("🖥 Dashboard", url=dash_url[:512]),
        ],
        [
            InlineKeyboardButton(
                "▶ Auto-pipe ALL",
                callback_data=f"{CALLBACK_PREFIX}apall:on",
            ),
            InlineKeyboardButton(
                "⏸ Auto-pipe ALL",
                callback_data=f"{CALLBACK_PREFIX}apall:off",
            ),
        ],
        [
            InlineKeyboardButton(
                "✅ Auto-approve ON",
                callback_data=f"{CALLBACK_PREFIX}aapr:on",
            ),
            InlineKeyboardButton(
                "⛔ Auto-approve OFF",
                callback_data=f"{CALLBACK_PREFIX}aapr:off",
            ),
        ],
        [
            InlineKeyboardButton("−", callback_data=f"{CALLBACK_PREFIX}lim:-1"),
            InlineKeyboardButton(f"dep {lim}", callback_data=f"{CALLBACK_PREFIX}noop"),
            InlineKeyboardButton("+", callback_data=f"{CALLBACK_PREFIX}lim:+1"),
        ],
        [
            InlineKeyboardButton("◀ type", callback_data=f"{CALLBACK_PREFIX}mt:-1"),
            InlineKeyboardButton("media", callback_data=f"{CALLBACK_PREFIX}noop"),
            InlineKeyboardButton("type ▶", callback_data=f"{CALLBACK_PREFIX}mt:+1"),
        ],
        [
            InlineKeyboardButton("5", callback_data=f"{CALLBACK_PREFIX}preset:5"),
            InlineKeyboardButton("15", callback_data=f"{CALLBACK_PREFIX}preset:15"),
            InlineKeyboardButton("25", callback_data=f"{CALLBACK_PREFIX}preset:25"),
            InlineKeyboardButton("50", callback_data=f"{CALLBACK_PREFIX}preset:50"),
        ],
    ]
    lane_keys = _lane_keys_page(page)
    lane_row: list[Any] = []
    for nk in lane_keys:
        em = category_emoji_for_network_key(nk)
        lane_row.append(
            InlineKeyboardButton(
                f"{em} {nk[:8]}",
                callback_data=f"{CALLBACK_PREFIX}dep:{nk}",
            )
        )
        if len(lane_row) == 2:
            rows.append(lane_row)
            lane_row = []
    if lane_row:
        rows.append(lane_row)
    nav: list[Any] = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀ Lanes", callback_data=f"{CALLBACK_PREFIX}page:{page - 1}"))
    inv_len = len([k for k in CONTENT_LANE_NETWORK_KEYS if k not in ("inbox", "packs")])
    if (page + 1) * LANES_PER_PAGE < inv_len:
        nav.append(InlineKeyboardButton("Lanes ▶", callback_data=f"{CALLBACK_PREFIX}page:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append(
        [
            InlineKeyboardButton("📤 Flush Q&A", callback_data=f"{CALLBACK_PREFIX}flush:qa"),
            InlineKeyboardButton("📦 Flush hub", callback_data=f"{CALLBACK_PREFIX}flush:hub"),
        ]
    )
    rows.append(
        [
            InlineKeyboardButton("📥 Inbox now", callback_data=f"{CALLBACK_PREFIX}run:inbox"),
            InlineKeyboardButton("🗄 Vault flush", callback_data=f"{CALLBACK_PREFIX}flush:vault"),
        ]
    )
    return InlineKeyboardMarkup(rows)


def queue_lane_deposit_from_master(
    db: Session,
    lane_key: str,
    *,
    limit: int | None = None,
    media_types: str | None = None,
) -> dict[str, Any]:
    from app.services.storage_topic_deposit import default_deposit_media_types, queue_storage_topic_deposit

    nk = (lane_key or "").strip().lower()
    row = storage_map_by_key().get(nk)
    if not row or not row.message_thread_id:
        return {"ok": False, "error": "unmapped_lane", "network_key": nk}
    lim = limit or get_deposit_limit()
    mt = media_types or get_deposit_media_types()
    qa_only = not hub_master_auto_approve_enabled()
    return queue_storage_topic_deposit(
        db,
        message_thread_id=int(row.message_thread_id),
        limit=lim,
        media_types=mt,
        include_topic_mirror=False,
        sent_cache=False,
        auto_pipe=False,
        qa_review_only=qa_only,
        commit=True,
    )


async def ensure_qa_master_panel_at_thread(
    bot,
    *,
    chat_id: int,
    message_thread_id: int,
    page: int = 0,
    force_new: bool = False,
) -> dict[str, Any]:
    """Singleton Q&A master panel in any Storage Hub forum subtopic (bottom of thread)."""
    from telegram.constants import ParseMode

    from app.database.session import SessionLocal
    from app.services.hub_panel_message import ensure_singleton_panel_message
    from app.utils.telegram_forum import normalize_hub_panel_thread_id

    cid = int(chat_id)
    tid = normalize_hub_panel_thread_id(message_thread_id)
    with SessionLocal() as db:
        text = format_qa_master_panel_html(db, page=page)
    markup = qa_master_panel_keyboard(page=page)

    return await ensure_singleton_panel_message(
        bot,
        chat_id=cid,
        message_thread_id=tid,
        text=text,
        parse_mode=ParseMode.HTML,
        reply_markup=markup,
        force_new=force_new,
        get_stored_message_id=lambda: get_stored_panel_message_id(cid, tid),
        set_stored_message_id=lambda mid: set_stored_panel_message_id(cid, tid, mid),
        panel_label="qa_master",
    )


async def ensure_qa_master_panel(bot, *, force_new: bool = False) -> dict[str, Any]:
    from app.data.aof_storage_hub_map import GATEKEEPER_REVIEW_TOPIC_ID
    from app.services.gatekeeper_review import review_chat_id

    chat_id = int(review_chat_id())
    thread_id = int(GATEKEEPER_REVIEW_TOPIC_ID or 1)
    return await ensure_qa_master_panel_at_thread(
        bot,
        chat_id=chat_id,
        message_thread_id=thread_id,
        force_new=force_new,
    )
