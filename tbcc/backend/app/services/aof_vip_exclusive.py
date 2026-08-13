"""VIP-exclusive window — newest pool media stays VIP-eligible before public lanes."""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any

from app.services.aof_vip_pool import is_vip_mirror_pool


def vip_exclusive_delay_enabled() -> bool:
    raw = (os.getenv("TBCC_VIP_EXCLUSIVE_DELAY_ENABLED") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def vip_exclusive_delay_days() -> int:
    raw = (os.getenv("TBCC_VIP_EXCLUSIVE_DELAY_DAYS") or "2").strip()
    try:
        return max(0, min(14, int(raw)))
    except ValueError:
        return 2


def vip_exclusive_target_pct() -> float:
    """Informational target for ops reporting (not enforced in v1)."""
    raw = (os.getenv("TBCC_VIP_EXCLUSIVE_TARGET_PCT") or "10").strip()
    try:
        return max(0.0, min(50.0, float(raw)))
    except ValueError:
        return 10.0


def public_exclusive_cutoff_utc() -> datetime | None:
    """Media with created_at after this cutoff is VIP-only on public mirror pools."""
    if not vip_exclusive_delay_enabled():
        return None
    days = vip_exclusive_delay_days()
    if days <= 0:
        return None
    return datetime.utcnow() - timedelta(days=days)


def media_eligible_for_public_exclusive(media, *, cutoff: datetime | None = None) -> bool:
    if cutoff is None:
        cutoff = public_exclusive_cutoff_utc()
    if cutoff is None:
        return True
    created = getattr(media, "created_at", None)
    if created is None:
        return True
    if getattr(created, "tzinfo", None) is not None:
        created = created.replace(tzinfo=None)
    return created <= cutoff


def filter_media_for_public_vip_exclusive(
    rows: list[Any],
    *,
    pool=None,
    cutoff: datetime | None = None,
) -> list[Any]:
    """Drop newest items from public sends on VIP mirror pools."""
    if pool is not None and not is_vip_mirror_pool(pool):
        return rows
    cutoff = public_exclusive_cutoff_utc() if cutoff is None else cutoff
    if cutoff is None:
        return rows
    return [m for m in rows if media_eligible_for_public_exclusive(m, cutoff=cutoff)]
