"""Tier gates + daily quotas for AOF keyword search."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Literal

from sqlalchemy.orm import Session

from app.services.aof_search_surfaces import AofSearchSurface, allowed_surfaces_for_tier, resolve_surface
from app.services.subscription_access import is_aof_vip_subscriber, is_loot_key_holder
from app.services.tbcc_operator_ids import is_tbcc_operator

SearchTier = Literal["operator", "vip", "loot_key", "free"]

_REDIS_PREFIX = "tbcc:aof_search"


def _redis_client():
    from app.services.content_signals import _redis_client as client

    return client()


def _int_env(name: str, default: int) -> int:
    raw = (os.getenv(name) or str(default)).strip()
    try:
        return max(0, int(raw))
    except ValueError:
        return default


def daily_limit_for_tier(tier: SearchTier) -> int:
    if tier == "operator":
        return _int_env("TBCC_AOF_SEARCH_OPERATOR_DAILY", 999)
    if tier == "vip":
        return _int_env("TBCC_AOF_SEARCH_VIP_DAILY", 999)
    if tier == "loot_key":
        return _int_env("TBCC_AOF_SEARCH_LOOT_DAILY", 10)
    return _int_env("TBCC_AOF_SEARCH_FREE_DAILY", 3)


def album_size_for_tier(tier: SearchTier) -> int:
    if tier in ("operator", "vip"):
        return _int_env("TBCC_AOF_SEARCH_VIP_ALBUM_SIZE", 12)
    if tier == "loot_key":
        return _int_env("TBCC_AOF_SEARCH_LOOT_ALBUM_SIZE", 6)
    return _int_env("TBCC_AOF_SEARCH_FREE_ALBUM_SIZE", 3)


def resolve_search_tier(db: Session, telegram_user_id: int) -> SearchTier:
    uid = int(telegram_user_id)
    if is_tbcc_operator(uid):
        return "operator"
    if is_aof_vip_subscriber(db, uid):
        return "vip"
    if is_loot_key_holder(db, uid):
        return "loot_key"
    return "free"


def _day_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d")


def _usage_key(telegram_user_id: int) -> str:
    return f"{_REDIS_PREFIX}:usage:{int(telegram_user_id)}:{_day_key()}"


def searches_used_today(telegram_user_id: int) -> int:
    try:
        r = _redis_client()
        if not r:
            return 0
        raw = r.get(_usage_key(telegram_user_id))
        return int(raw or 0)
    except Exception:
        return 0


def consume_search_quota(telegram_user_id: int, *, limit: int) -> dict[str, Any]:
    if limit >= 999:
        return {"ok": True, "used": searches_used_today(telegram_user_id), "limit": limit}
    try:
        r = _redis_client()
        if not r:
            return {"ok": True, "used": 0, "limit": limit, "note": "redis_unavailable"}
        key = _usage_key(telegram_user_id)
        used = int(r.get(key) or 0)
        if used >= limit:
            return {
                "ok": False,
                "reason": "daily_limit",
                "used": used,
                "limit": limit,
            }
        pipe = r.pipeline()
        pipe.incr(key)
        pipe.expire(key, 86400 * 2)
        pipe.execute()
        return {"ok": True, "used": used + 1, "limit": limit}
    except Exception:
        return {"ok": True, "used": 0, "limit": limit, "note": "redis_error"}


def evaluate_search_access(
    db: Session,
    telegram_user_id: int,
    *,
    surface: str | None = None,
) -> dict[str, Any]:
    uid = int(telegram_user_id)
    tier = resolve_search_tier(db, uid)
    is_vip = tier in ("vip", "operator")
    is_loot = tier in ("loot_key", "vip", "operator")
    is_op = tier == "operator"
    resolved = resolve_surface(
        surface,
        is_vip=is_vip,
        is_loot_key=is_loot,
        is_operator=is_op,
    )
    limit = daily_limit_for_tier(tier)
    used = searches_used_today(uid)
    album_size = album_size_for_tier(tier)
    return {
        "tier": tier,
        "surface": resolved,
        "allowed_surfaces": allowed_surfaces_for_tier(
            is_vip=is_vip, is_loot_key=is_loot, is_operator=is_op
        ),
        "daily_limit": limit,
        "searches_used_today": used,
        "searches_remaining": max(0, limit - used) if limit < 999 else 999,
        "album_size": album_size,
        "can_search": resolved is not None and (used < limit or limit >= 999),
    }
