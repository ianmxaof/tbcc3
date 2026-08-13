"""Operator-tunable /deposit presets — limit + media type (Redis-backed)."""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

REDIS_PREFIX = "tbcc:storage:deposit:ctrl"
LIMIT_STEP = 50
LIMIT_MIN = 50
LIMIT_MAX = 200
MEDIA_TYPES = ("videos", "photos", "both")
MEDIA_LABELS = {"videos": "video", "photos": "image", "both": "both"}
PRESET_LIMITS = (50, 100, 150)


def _redis():
    import redis

    url = (os.getenv("REDIS_URL") or "redis://localhost:6379/0").strip()
    return redis.from_url(url, decode_responses=True, socket_connect_timeout=2)


def _key(suffix: str) -> str:
    return f"{REDIS_PREFIX}:{suffix}"


def _env_limit_default() -> int:
    raw = (os.getenv("TBCC_STORAGE_DEPOSIT_PRESET_LIMIT") or "50").strip()
    try:
        val = int(raw)
    except ValueError:
        val = 50
    return _snap_limit(val)


def _env_media_default() -> str:
    from app.services.storage_topic_deposit import default_deposit_media_types

    raw = default_deposit_media_types()
    return raw if raw in MEDIA_TYPES else "both"


def _snap_limit(value: int) -> int:
    val = int(value)
    if val <= LIMIT_MIN:
        return LIMIT_MIN
    steps = round((val - LIMIT_MIN) / LIMIT_STEP)
    snapped = LIMIT_MIN + steps * LIMIT_STEP
    return min(max(snapped, LIMIT_MIN), LIMIT_MAX)


def get_deposit_limit() -> int:
    try:
        raw = _redis().get(_key("limit"))
        if raw is not None:
            return _snap_limit(int(raw))
    except Exception:
        logger.debug("deposit control limit read failed", exc_info=True)
    return _env_limit_default()


def set_deposit_limit(value: int) -> int:
    val = _snap_limit(value)
    try:
        _redis().set(_key("limit"), str(val))
    except Exception:
        logger.debug("deposit control limit write failed", exc_info=True)
    return val


def adjust_deposit_limit(delta_steps: int) -> int:
    cur = get_deposit_limit()
    return set_deposit_limit(cur + int(delta_steps) * LIMIT_STEP)


def get_deposit_media_types() -> str:
    try:
        raw = (_redis().get(_key("media")) or "").strip().lower()
        if raw in MEDIA_TYPES:
            return raw
    except Exception:
        logger.debug("deposit control media read failed", exc_info=True)
    return _env_media_default()


def set_deposit_media_types(value: str) -> str:
    val = (value or "").strip().lower()
    if val not in MEDIA_TYPES:
        val = _env_media_default()
    try:
        _redis().set(_key("media"), val)
    except Exception:
        logger.debug("deposit control media write failed", exc_info=True)
    return val


def cycle_deposit_media_types(direction: int) -> str:
    cur = get_deposit_media_types()
    try:
        idx = MEDIA_TYPES.index(cur)
    except ValueError:
        idx = 0
    step = 1 if int(direction) >= 0 else -1
    nxt = MEDIA_TYPES[(idx + step) % len(MEDIA_TYPES)]
    return set_deposit_media_types(nxt)


def media_type_label(media_types: str | None = None) -> str:
    key = (media_types or get_deposit_media_types()).strip().lower()
    return MEDIA_LABELS.get(key, key)


def format_deposit_command(limit: int | None = None, media_types: str | None = None) -> str:
    lim = limit if limit is not None else get_deposit_limit()
    mt = media_type_label(media_types)
    return f"/deposit {lim} {mt}"


def format_deposit_panel_html(*, thread_title: str | None = None) -> str:
    lim = get_deposit_limit()
    mt = get_deposit_media_types()
    label = media_type_label(mt)
    topic_line = f"<b>Topic:</b> {thread_title}\n" if thread_title else ""
    return (
        "<b>📥 Storage deposit panel</b>\n\n"
        f"{topic_line}"
        f"<b>Count:</b> {lim} · <b>Type:</b> <code>{label}</code>\n"
        f"Command: <code>{format_deposit_command(lim, mt)}</code>\n\n"
        "<i>Pinned in every Storage lane. Use − / + then Deposit or a preset.</i>"
    )


def deposit_control_keyboard() -> dict[str, Any]:
    """Inline keyboard dict (Bot API shape) for deposit panel."""
    lim = get_deposit_limit()
    mt_label = media_type_label()
    rows = [
        [
            {"text": "−", "callback_data": "depctl:lim:-1"},
            {"text": str(lim), "callback_data": "depctl:noop"},
            {"text": "+", "callback_data": "depctl:lim:+1"},
        ],
        [
            {"text": "−", "callback_data": "depctl:mt:-1"},
            {"text": mt_label, "callback_data": "depctl:noop"},
            {"text": "+", "callback_data": "depctl:mt:+1"},
        ],
        [
            {
                "text": f"📥 Deposit {lim} {mt_label}",
                "callback_data": "depctl:run",
            }
        ],
    ]
    preset_row = [
        {"text": f"{n} {media_type_label()}", "callback_data": f"depctl:preset:{n}"}
        for n in PRESET_LIMITS
    ]
    rows.append(preset_row)
    rows.append([{"text": "🔄 Refresh", "callback_data": "depctl:refresh"}])
    return {"inline_keyboard": rows}


def deposit_control_inline_markup():
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    kb = deposit_control_keyboard()
    rows = [
        [InlineKeyboardButton(b["text"], callback_data=b["callback_data"]) for b in row]
        for row in kb.get("inline_keyboard") or []
    ]
    return InlineKeyboardMarkup(rows)
