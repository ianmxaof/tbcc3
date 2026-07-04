"""VIP mirror pool classification — kept separate from aof_vip_mirror to avoid import cycles."""

from __future__ import annotations

from app.data.aof_network import AOF_NETWORK_CHANNELS, AOF_VIP_POOL_NAME

PACKS_POOL_NAME = "AOF PACKS — Promo"


def vip_mirror_pool_names() -> frozenset[str]:
    names = {ch.pool_name for ch in AOF_NETWORK_CHANNELS}
    names.add(PACKS_POOL_NAME)
    return frozenset(names)


def is_vip_mirror_pool(pool) -> bool:
    if not pool or not getattr(pool, "name", None):
        return False
    if str(pool.name) == AOF_VIP_POOL_NAME:
        return False
    return str(pool.name) in vip_mirror_pool_names()
