"""Emoji lane multi-select for gatekeeper quarantine approve."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from app.data.aof_storage_hub_map import (
    CONTENT_LANE_NETWORK_KEYS,
    category_emoji_for_network_key,
)

logger = logging.getLogger(__name__)

CALLBACK_TOGGLE = "gk:t:"
CALLBACK_APPROVE = "gk:a:"
CALLBACK_REJECT = "gk:r:"
LANE_PICK_REDIS_PREFIX = "tbcc:gk:lanes"
LANE_PICK_TTL_SECONDS = 86400 * 7

# Short Telegram button labels (emoji + lane key).
LANE_BUTTON_SHORT: dict[str, str] = {
    "ass": "ASS",
    "big_tits": "TITS",
    "blowjob": "BJ",
    "bop": "BOP",
    "goon": "GOON",
    "ai": "AI",
    "milf": "MILF",
    "voyeur": "VOY",
    "taboo": "TAB",
    "abg": "ABG",
    "full_length": "FULL",
}


def lane_picker_enabled() -> bool:
    return (os.getenv("TBCC_GATEKEEPER_LANE_PICKER") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def gatekeeper_lane_picker_keys() -> list[str]:
    """Content lanes operators can assign on approve (excludes inbox + packs)."""
    raw = (os.getenv("TBCC_GATEKEEPER_LANE_PICKER_KEYS") or "").strip()
    if raw:
        wanted = {x.strip().lower() for x in raw.split(",") if x.strip()}
        return sorted(k for k in wanted if k in CONTENT_LANE_NETWORK_KEYS and k not in ("inbox", "packs"))
    return sorted(k for k in CONTENT_LANE_NETWORK_KEYS if k not in ("inbox", "packs"))


def _redis():
    import redis

    url = (os.getenv("REDIS_URL") or "redis://localhost:6379/0").strip()
    return redis.from_url(url, decode_responses=True, socket_connect_timeout=2)


def _lane_pick_key(media_id: int) -> str:
    return f"{LANE_PICK_REDIS_PREFIX}:{int(media_id)}"


def get_picked_lanes(media_id: int) -> list[str]:
    try:
        raw = _redis().get(_lane_pick_key(media_id))
        if not raw:
            return []
        data = json.loads(raw)
        if isinstance(data, list):
            return sorted({str(x).strip().lower() for x in data if str(x).strip()})
    except Exception:
        logger.debug("lane pick read failed media_id=%s", media_id, exc_info=True)
    return []


def set_picked_lanes(media_id: int, lanes: list[str]) -> list[str]:
    clean = sorted({(x or "").strip().lower() for x in lanes if (x or "").strip()})
    try:
        r = _redis()
        key = _lane_pick_key(media_id)
        if clean:
            r.set(key, json.dumps(clean), ex=LANE_PICK_TTL_SECONDS)
        else:
            r.delete(key)
    except Exception:
        logger.debug("lane pick write failed media_id=%s", media_id, exc_info=True)
    return clean


def toggle_picked_lane(media_id: int, lane_key: str) -> list[str]:
    key = (lane_key or "").strip().lower()
    if key not in gatekeeper_lane_picker_keys():
        return get_picked_lanes(media_id)
    current = set(get_picked_lanes(media_id))
    if key in current:
        current.remove(key)
    else:
        current.add(key)
    return set_picked_lanes(media_id, sorted(current))


def clear_picked_lanes(media_id: int) -> None:
    try:
        _redis().delete(_lane_pick_key(media_id))
    except Exception:
        logger.debug("lane pick clear failed media_id=%s", media_id, exc_info=True)


def lane_button_label(lane_key: str, *, selected: bool = False) -> str:
    emoji = category_emoji_for_network_key(lane_key)
    short = LANE_BUTTON_SHORT.get(lane_key, lane_key.upper()[:6])
    prefix = "✅ " if selected else ""
    return f"{prefix}{emoji} {short}"


def review_lane_picker_keyboard(
    media_id: int,
    selected: list[str] | None = None,
    default_lane_key: str | None = None,
) -> dict[str, Any]:
    """Inline keyboard: emoji lane toggles + approve/reject."""
    from app.services.gatekeeper_review import panel_open_callback

    mid = int(media_id)
    picked = set(selected if selected is not None else get_picked_lanes(mid))
    lanes = gatekeeper_lane_picker_keys()
    rows: list[list[dict[str, str]]] = []
    row: list[dict[str, str]] = []
    for lane in lanes:
        row.append(
            {
                "text": lane_button_label(lane, selected=lane in picked),
                "callback_data": f"{CALLBACK_TOGGLE}{mid}:{lane}",
            }
        )
        if len(row) >= 4:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append(
        [
            {"text": "✅ Approve", "callback_data": f"{CALLBACK_APPROVE}{mid}"},
            {"text": "🗑 Reject", "callback_data": f"{CALLBACK_REJECT}{mid}"},
        ]
    )
    lane_for_open = (default_lane_key or "").strip().lower() or None
    if not lane_for_open and picked:
        lane_for_open = sorted(picked)[0]
    rows.append(
        [{"text": "📋 Review all waiting", "callback_data": panel_open_callback(lane_for_open)}]
    )
    return {"inline_keyboard": rows}


def format_lane_pick_hint(selected: list[str]) -> str:
    if not selected:
        return "Tap lane emoji(s), then Approve."
    stamps = " ".join(category_emoji_for_network_key(l) for l in selected)
    return f"Lanes: {stamps} ({', '.join(selected)})"
