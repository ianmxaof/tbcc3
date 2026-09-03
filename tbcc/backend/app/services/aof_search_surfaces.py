"""Search surfaces — Archive of Filth library, Loot Room lanes, AOF VIP."""

from __future__ import annotations

from typing import Literal

from sqlalchemy.orm import Session

from app.data.aof_library_forum_topic_map import AOF_LIBRARY_FORUM_TOPIC_MAP
from app.data.aof_network import (
    AOF_FULL_LENGTH_POOL_NAME,
    AOF_NETWORK_CHANNELS,
    AOF_VIP_POOL_NAME,
)

AofSearchSurface = Literal["loot_room", "library", "vip"]

_LIBRARY_LANE_KEYS: frozenset[str] = frozenset(
    row.network_key for row in AOF_LIBRARY_FORUM_TOPIC_MAP
)

_POOL_NAME_BY_LANE: dict[str, str] = {ch.key: ch.pool_name for ch in AOF_NETWORK_CHANNELS}


def pool_names_for_lane_keys(lane_keys: set[str] | frozenset[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for key in lane_keys:
        name = _POOL_NAME_BY_LANE.get((key or "").strip().lower())
        if name and name not in seen:
            seen.add(name)
            out.append(name)
    return out


def pool_names_for_surface(surface: AofSearchSurface) -> list[str]:
    lane_pools = pool_names_for_lane_keys(_LIBRARY_LANE_KEYS)
    loot_lane_pools = [
        ch.pool_name
        for ch in AOF_NETWORK_CHANNELS
        if ch.key not in ("main", "inbox")
    ]
    if surface == "vip":
        return list(
            dict.fromkeys([AOF_VIP_POOL_NAME, AOF_FULL_LENGTH_POOL_NAME] + lane_pools + loot_lane_pools)
        )
    if surface == "library":
        return lane_pools
    return loot_lane_pools


def pool_ids_for_surface(db: Session, surface: AofSearchSurface) -> list[int]:
    from app.models.content_pool import ContentPool

    names = pool_names_for_surface(surface)
    if not names:
        return []
    rows = db.query(ContentPool.id, ContentPool.name).filter(ContentPool.name.in_(names)).all()
    by_name = {str(name): int(pid) for pid, name in rows}
    ids = [by_name[n] for n in names if n in by_name]
    if surface != "loot_room":
        return ids

    from app.models.loot import LootPoolEligibility

    enabled = (
        db.query(LootPoolEligibility.content_pool_id)
        .filter(LootPoolEligibility.loot_enabled.is_(True))
        .all()
    )
    enabled_ids = {int(r[0]) for r in enabled}
    if not enabled_ids:
        return ids
    filtered = [pid for pid in ids if pid in enabled_ids]
    return filtered or ids


def allowed_surfaces_for_tier(*, is_vip: bool, is_loot_key: bool, is_operator: bool) -> list[AofSearchSurface]:
    if is_operator or is_vip:
        return ["loot_room", "library", "vip"]
    if is_loot_key:
        return ["loot_room", "library"]
    return ["loot_room"]


def resolve_surface(
    requested: str | None,
    *,
    is_vip: bool,
    is_loot_key: bool,
    is_operator: bool,
) -> AofSearchSurface | None:
    allowed = allowed_surfaces_for_tier(
        is_vip=is_vip, is_loot_key=is_loot_key, is_operator=is_operator
    )
    raw = (requested or "loot_room").strip().lower()
    if raw in ("loot", "loot_room", "room"):
        raw = "loot_room"
    if raw in ("archive", "aof", "filth"):
        raw = "library"
    if raw not in ("loot_room", "library", "vip"):
        raw = allowed[0]
    if raw not in allowed:
        return None
    return raw  # type: ignore[return-value]
