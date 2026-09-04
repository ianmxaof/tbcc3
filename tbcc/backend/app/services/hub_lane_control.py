"""Per-lane Storage Hub controls (auto-pipe, Loot Room preview toggles)."""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

REDIS_PREFIX = "tbcc:hub:lane"


def _redis():
    import redis

    url = (os.getenv("REDIS_URL") or "redis://localhost:6379/0").strip()
    return redis.from_url(url, decode_responses=True, socket_connect_timeout=2)


def _lane_key(lane_key: str) -> str:
    return (lane_key or "").strip().lower()


def lane_loot_preview_enabled(lane_key: str) -> bool:
    """When false, sent-cache composer skips Loot Room for this lane only."""
    key = _lane_key(lane_key)
    if not key:
        return True
    try:
        raw = (_redis().get(f"{REDIS_PREFIX}:{key}:loot_preview") or "").strip().lower()
        if raw in ("0", "false", "no", "off"):
            return False
        if raw in ("1", "true", "yes", "on"):
            return True
    except Exception:
        logger.debug("lane loot preview read failed lane=%s", key, exc_info=True)
    env_default = (os.getenv("TBCC_LANE_LOOT_PREVIEW_DEFAULT") or "1").strip().lower()
    return env_default not in ("0", "false", "no", "off")


def set_lane_loot_preview_enabled(lane_key: str, enabled: bool) -> bool:
    key = _lane_key(lane_key)
    if not key:
        return enabled
    try:
        _redis().set(f"{REDIS_PREFIX}:{key}:loot_preview", "1" if enabled else "0")
    except Exception:
        logger.debug("lane loot preview write failed lane=%s", key, exc_info=True)
    return enabled


def format_lane_hub_panel_html(
    *,
    thread_title: str | None,
    network_key: str | None,
    live_topics: list[dict] | None = None,
) -> str:
    from app.services.main_group_topic_resolve import format_loot_room_topic_status
    from app.services.storage_auto_pipe import auto_pipe_debounce_s, lane_auto_pipe_enabled
    from app.services.storage_deposit_control import (
        format_deposit_command,
        get_deposit_limit,
        get_deposit_media_types,
        media_type_label,
    )
    from app.services.sent_cache_control import preview_max_loot_albums_per_run

    nk = _lane_key(network_key or "")
    lim = get_deposit_limit()
    mt = media_type_label(get_deposit_media_types())
    topic_line = f"<b>Topic:</b> {thread_title}\n" if thread_title else ""
    autopipe = lane_auto_pipe_enabled(nk) if nk else False
    preview_on = lane_loot_preview_enabled(nk) if nk else True
    loot_line = format_loot_room_topic_status(nk, live_topics=live_topics) if nk else "—"
    lines = [
        "<b>📥 Lane control panel</b>\n\n",
        f"{topic_line}"
        f"<b>Lane:</b> <code>{nk or '?'}</code>\n"
        f"<b>Deposit:</b> {lim} · <code>{mt}</code> — <code>{format_deposit_command(lim, get_deposit_media_types())}</code>\n"
        f"<b>Auto-pipe:</b> {'ON' if autopipe else 'OFF'} (debounce {auto_pipe_debounce_s()}s)\n"
        f"<b>Loot preview:</b> {'ON' if preview_on else 'OFF'} (max {preview_max_loot_albums_per_run()} album(s)/deposit)\n"
        f"<b>Loot subtopic:</b> {loot_line}\n",
    ]
    if nk:
        from app.services.lane_composer_status import format_lane_composer_status_line

        composer_line = format_lane_composer_status_line(nk)
        if composer_line:
            lines.append(f"{composer_line}\n")
    lines.append("\n<i>Deposit imports to pool + SENT VAULT. Loot previews are capped — schedulers own the feed cadence.</i>")
    return "".join(lines)


def lane_hub_control_keyboard(network_key: str | None) -> Any:
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    from app.services.storage_auto_pipe import lane_auto_pipe_enabled

    nk = _lane_key(network_key or "")
    rows = [
        [
            InlineKeyboardButton("−", callback_data="hubctl:lim:-1"),
            InlineKeyboardButton("count", callback_data="hubctl:noop"),
            InlineKeyboardButton("+", callback_data="hubctl:lim:+1"),
        ],
        [
            InlineKeyboardButton("− type", callback_data="hubctl:mt:-1"),
            InlineKeyboardButton("media", callback_data="hubctl:noop"),
            InlineKeyboardButton("+ type", callback_data="hubctl:mt:+1"),
        ],
        [
            InlineKeyboardButton("🚿 Drain this lane", callback_data="hubctl:drain"),
        ],
    ]
    if nk:
        if lane_auto_pipe_enabled(nk):
            rows.append([InlineKeyboardButton("⏸ Auto-pipe OFF", callback_data=f"hubctl:autopipe:off:{nk}")])
        else:
            rows.append([InlineKeyboardButton("▶ Auto-pipe ON", callback_data=f"hubctl:autopipe:on:{nk}")])
        if lane_loot_preview_enabled(nk):
            rows.append([InlineKeyboardButton("⏸ Loot preview OFF", callback_data=f"hubctl:preview:off:{nk}")])
        else:
            rows.append([InlineKeyboardButton("▶ Loot preview ON", callback_data=f"hubctl:preview:on:{nk}")])
    rows.append(
        [
            InlineKeyboardButton("🔗 Preview rebundle", callback_data="hubctl:rebundle:preview"),
            InlineKeyboardButton("✅ Rebundle (+partial)", callback_data="hubctl:rebundle:run"),
        ]
    )
    rows.append(
        [
            InlineKeyboardButton("🟡 Master panel", callback_data="hubctl:master"),
            InlineKeyboardButton("🔄 Refresh", callback_data="hubctl:refresh"),
        ]
    )
    rows.append(
        [
            InlineKeyboardButton("50", callback_data="hubctl:preset:50"),
            InlineKeyboardButton("100", callback_data="hubctl:preset:100"),
        ]
    )
    return InlineKeyboardMarkup(rows)
