"""VIP channel early-drop: post to AOF VIP before public network lanes."""

from __future__ import annotations

import logging
import os

from sqlalchemy.orm import Session

from app.data.aof_network import AOF_VIP_IDENT, AOF_VIP_POOL_NAME

logger = logging.getLogger(__name__)


def vip_early_drop_enabled() -> bool:
    raw = (os.getenv("TBCC_AOF_VIP_EARLY_DROP_ENABLED") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def vip_early_drop_minutes() -> int:
    try:
        n = int((os.getenv("TBCC_AOF_VIP_EARLY_DROP_MINUTES") or "60").strip())
    except ValueError:
        n = 60
    return max(0, min(n, 24 * 60))


def vip_early_drop_seconds() -> int:
    return vip_early_drop_minutes() * 60


def is_aof_public_network_pool(pool) -> bool:
    from app.services.aof_vip_pool import is_vip_mirror_pool

    return is_vip_mirror_pool(pool)


def should_schedule_vip_early_drop(pool) -> bool:
    from app.services.aof_vip_pool import is_vip_mirror_pool

    return vip_early_drop_enabled() and is_vip_mirror_pool(pool)


def vip_channel_identifier(db: Session) -> str | None:
    from app.models.channel import Channel
    from app.services.aof_vip_checkout import vip_channel_ident

    ident = vip_channel_ident()
    row = db.query(Channel).filter(Channel.identifier == ident).first()
    if row:
        return row.identifier
    return ident or None
