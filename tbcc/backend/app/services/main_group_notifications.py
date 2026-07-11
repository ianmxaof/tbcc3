"""Main-group notification budget — at most one loud post per rolling window."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from app.data.aof_network import MAIN_GROUP_IDENT

logger = logging.getLogger(__name__)

REDIS_NOTIFY_KEY = "tbcc:main_group:last_loud_notify"


def main_group_notify_gate_enabled() -> bool:
    return (os.getenv("TBCC_MAIN_GROUP_NOTIFY_GATE") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def notify_window_hours() -> float:
    raw = (os.getenv("TBCC_MAIN_GROUP_NOTIFY_WINDOW_HOURS") or "4").strip()
    try:
        return max(1.0, min(24.0, float(raw)))
    except ValueError:
        return 4.0


def _redis():
    import redis

    url = (os.getenv("REDIS_URL") or "redis://localhost:6379/0").strip()
    return redis.from_url(url, decode_responses=True, socket_connect_timeout=2)


def is_main_group_identifier(channel_identifier: str | None) -> bool:
    ident = str(channel_identifier or "").strip()
    if not ident:
        return False
    try:
        return int(ident) == int(MAIN_GROUP_IDENT)
    except ValueError:
        return ident == MAIN_GROUP_IDENT


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _last_loud_at() -> datetime | None:
    try:
        r = _redis()
        raw = r.get(REDIS_NOTIFY_KEY)
        if not raw:
            return None
        return datetime.fromisoformat(str(raw).replace("Z", ""))
    except Exception as e:
        logger.debug("commons notify gate read: %s", e)
        return None


def _record_loud_notify() -> None:
    try:
        r = _redis()
        now = _utcnow().isoformat() + "Z"
        ttl = int(notify_window_hours() * 3600) + 3600
        r.set(REDIS_NOTIFY_KEY, now, ex=ttl)
    except Exception as e:
        logger.debug("commons notify gate write: %s", e)


def resolve_main_group_send_silent(
    *,
    channel_identifier: str | None,
    post_send_silent: bool,
    had_media: bool = False,
) -> bool:
    """
    Return True when Telegram should send with disable_notification (silent).

  Main group: even when post.send_silent is False, only the first eligible send
  inside the rolling window may notify; subsequent posts are forced silent.
    """
    if not is_main_group_identifier(channel_identifier):
        return bool(post_send_silent)
    if not main_group_notify_gate_enabled():
        return bool(post_send_silent)
    if post_send_silent:
        return True

    last = _last_loud_at()
    window = timedelta(hours=notify_window_hours())
    if last and _utcnow() - last < window:
        logger.info(
            "commons notify gate: forcing silent (last loud %s ago, window %.1fh, media=%s)",
            _utcnow() - last,
            notify_window_hours(),
            had_media,
        )
        return True

    _record_loud_notify()
    logger.info("commons notify gate: allowing loud send (media=%s)", had_media)
    return False


def main_group_notify_status() -> dict[str, Any]:
    last = _last_loud_at()
    window = notify_window_hours()
    next_loud_at = None
    if last:
        next_loud_at = (last + timedelta(hours=window)).isoformat() + "Z"
    return {
        "enabled": main_group_notify_gate_enabled(),
        "window_hours": window,
        "last_loud_at": last.isoformat() + "Z" if last else None,
        "next_loud_eligible_at": next_loud_at,
    }
