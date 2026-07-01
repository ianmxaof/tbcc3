"""AOF Feed Rhythm v2 — main-group tease albums, VIP roll sizing, post-trigger storage refill."""

from __future__ import annotations

import logging
import os
import random
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.data.aof_network import AOF_NETWORK_CHANNELS, AOF_VIP_IDENT, AOF_VIP_POOL_NAME, MAIN_GROUP_IDENT
from app.models.channel import Channel
from app.models.content_pool import ContentPool
from app.models.media import Media
from app.models.scheduled_text_post import ScheduledTextPost

logger = logging.getLogger(__name__)

LIVENESS_PREFIX = "AOF — network liveness"
FEED_RHYTHM_INTERJECTION_NAME = "AOF — feed rhythm interjection"
MILESTONE_FOMO_SUFFIX = "milestone FOMO"

_NETWORK_POOL_NAMES = frozenset(
    nc.pool_name for nc in AOF_NETWORK_CHANNELS if nc.key not in ("main", "packs")
)
_POOL_NAME_TO_KEY = {nc.pool_name: nc.key for nc in AOF_NETWORK_CHANNELS}


def network_album_size() -> int:
    raw = (os.getenv("TBCC_NETWORK_ALBUM_SIZE") or "3").strip()
    try:
        return max(1, min(10, int(raw)))
    except ValueError:
        return 3


def main_group_album_size() -> int:
    raw = (os.getenv("TBCC_MAIN_GROUP_ALBUM_SIZE") or "").strip()
    if raw:
        try:
            return max(1, min(10, int(raw)))
        except ValueError:
            pass
    return network_album_size()


def vip_album_roll_min() -> int:
    raw = (os.getenv("TBCC_AOF_VIP_ALBUM_ROLL_MIN") or "3").strip()
    try:
        return max(1, min(10, int(raw)))
    except ValueError:
        return 3


def vip_album_roll_max() -> int:
    raw = (os.getenv("TBCC_AOF_VIP_ALBUM_ROLL_MAX") or "10").strip()
    try:
        return max(vip_album_roll_min(), min(10, int(raw)))
    except ValueError:
        return 10


def vip_album_roll_enabled() -> bool:
    raw = (os.getenv("TBCC_AOF_VIP_ALBUM_ROLL") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def post_refill_probability() -> float:
    raw = (os.getenv("TBCC_POST_REFILL_PROBABILITY") or "0.30").strip()
    try:
        return max(0.0, min(1.0, float(raw)))
    except ValueError:
        return 0.30


def post_refill_batch() -> int:
    raw = (os.getenv("TBCC_POST_REFILL_BATCH") or "3").strip()
    try:
        return max(1, min(50, int(raw)))
    except ValueError:
        return 3


def _weighted_choice(items: list[int], weights: list[float], rng: random.Random) -> int:
    if not items:
        return main_group_album_size()
    total = sum(max(0.0, float(w)) for w in weights)
    if total <= 0:
        return items[0]
    target = rng.random() * total
    run = 0.0
    for item, w in zip(items, weights):
        run += max(0.0, float(w))
        if run >= target:
            return item
    return items[-1]


def roll_vip_album_size(*, seed: int | None = None) -> int:
    """Loot-style weighted roll — biased toward smaller albums inside min..max."""
    rng = random.Random(seed)
    lo = vip_album_roll_min()
    hi = vip_album_roll_max()
    sizes = list(range(lo, hi + 1))
    # Quadratic bias: 3 is common, 10 is rare.
    weights = [float((hi + 1 - size) ** 2) for size in sizes]
    return _weighted_choice(sizes, weights, rng)


def resolve_vip_album_size(*, pool_id: int | None = None) -> int:
    """Fixed env size when roll disabled; otherwise roll per send."""
    if not vip_album_roll_enabled():
        try:
            n = int((os.getenv("TBCC_AOF_VIP_ALBUM_SIZE") or "3").strip())
        except ValueError:
            n = 3
        return max(1, min(n, 10))
    seed = None
    if pool_id is not None:
        day = datetime.now(timezone.utc).strftime("%Y%m%d")
        seed = hash((int(pool_id), day, os.getpid())) & 0x7FFFFFFF
    return roll_vip_album_size(seed=seed)


def is_network_tease_scheduler(post: ScheduledTextPost | None) -> bool:
    if not post:
        return False
    name = (getattr(post, "name", None) or "").strip()
    if not name:
        return False
    if name == FEED_RHYTHM_INTERJECTION_NAME:
        return True
    if MILESTONE_FOMO_SUFFIX in name.lower():
        return True
    if name.startswith(LIVENESS_PREFIX):
        return True
    return False


def pick_network_lane_pool_id(db: Session) -> int | None:
    """Random AOF content-lane pool with at least one approved media row."""
    rows = (
        db.query(ContentPool.id)
        .join(Media, Media.pool_id == ContentPool.id)
        .filter(
            Media.status == "approved",
            ContentPool.name.in_(sorted(_NETWORK_POOL_NAMES)),
        )
        .distinct()
        .all()
    )
    ids = [int(r[0]) for r in rows]
    if not ids:
        return None
    return random.choice(ids)


def network_key_for_pool_name(pool_name: str | None) -> str | None:
    if not pool_name:
        return None
    return _POOL_NAME_TO_KEY.get(str(pool_name))


def apply_main_group_tease_media(sched: ScheduledTextPost) -> None:
    """Attach rotating 3-item network lane albums to main-group conversion schedulers."""
    sched.pool_collective_random = True
    sched.pool_id = None
    sched.album_size = main_group_album_size()
    sched.pool_randomize = True


def _approved_counts_for_pool(db: Session, pool_id: int) -> tuple[int, int]:
    photos = (
        db.query(func.count(Media.id))
        .filter(
            Media.pool_id == pool_id,
            Media.status == "approved",
            Media.media_type == "photo",
        )
        .scalar()
        or 0
    )
    videos = (
        db.query(func.count(Media.id))
        .filter(
            Media.pool_id == pool_id,
            Media.status == "approved",
            Media.media_type == "video",
        )
        .scalar()
        or 0
    )
    return int(photos), int(videos)


def _channel_age_days(channel: Channel | None) -> int | None:
    if not channel:
        return None
    created = getattr(channel, "created_at", None)
    if not created:
        return None
    now = datetime.now(timezone.utc)
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    return max(1, (now - created).days)


def vip_social_proof_line(db: Session) -> str:
    """One-line stat tease: VIP channel media density vs main group."""
    vip_pool = db.query(ContentPool).filter(ContentPool.name == AOF_VIP_POOL_NAME).first()
    main_pool = None
    for nc in AOF_NETWORK_CHANNELS:
        if nc.key == "main":
            main_pool = db.query(ContentPool).filter(ContentPool.name == nc.pool_name).first()
            break
    vip_ch = db.query(Channel).filter(Channel.identifier == AOF_VIP_IDENT).first()
    main_ch = db.query(Channel).filter(Channel.identifier == MAIN_GROUP_IDENT).first()

    if vip_pool:
        vp, vv = _approved_counts_for_pool(db, int(vip_pool.id))
        vip_total = vp + vv
    else:
        vp, vv, vip_total = 0, 0, 0

    if main_pool:
        mp, mv = _approved_counts_for_pool(db, int(main_pool.id))
        main_total = mp + mv
    else:
        main_total = 0

    vip_days = _channel_age_days(vip_ch) or 14
    main_days = _channel_age_days(main_ch) or 180

    if vip_total > 0:
        return (
            f"⭐ <b>VIP goldmine</b> — {vp:,} photos · {vv:,} videos in ~{vip_days}d "
            f"(main: {main_total:,} in ~{main_days}d). Rolls <b>3–10</b> per drop · early · ad-free."
        )
    return (
        "⭐ <b>AOF VIP</b> — standalone channel: bigger rolled albums (3–10), early drops, "
        "full stack directory. Pay ⭐ below."
    )


def vip_roll_tease_line(lane_name: str, *, public_size: int | None = None) -> str:
    lane = lane_name.strip() or "this lane"
    pub = public_size if public_size is not None else main_group_album_size()
    lo = vip_album_roll_min()
    hi = vip_album_roll_max()
    return (
        f"🎲 <b>{lane}</b> — public tease: {pub}. VIP rolls <b>{lo}–{hi}</b> from the same pool, ~1h early."
    )


def maybe_queue_post_refill(
    db: Session,
    *,
    pool_id: int,
    phase: str | None = None,
) -> dict[str, Any]:
    """Probabilistic storage-hub deposit after a successful lane/VIP pool post."""
    if phase == "vip":
        # VIP posts don't consume public queue — still seed the lane pool occasionally.
        pass
    if random.random() > post_refill_probability():
        return {"ok": True, "skipped": True, "reason": "probability"}

    pool = db.query(ContentPool).filter(ContentPool.id == int(pool_id)).first()
    if not pool:
        return {"ok": False, "error": "pool_missing"}

    network_key = network_key_for_pool_name(getattr(pool, "name", None))
    if not network_key or network_key in ("main", "packs", "full_length"):
        return {"ok": True, "skipped": True, "reason": "not_content_lane", "pool": pool.name}

    from app.services.aof_growth_hub import queue_storage_hub_deposits

    report = queue_storage_hub_deposits(
        db,
        limit=post_refill_batch(),
        topic_keys=[network_key],
        include_topic_mirror=False,
    )
    logger.info(
        "post-refill queued pool=%s key=%s batch=%s jobs=%s",
        pool_id,
        network_key,
        post_refill_batch(),
        report.get("matched_count"),
    )
    return {"ok": True, "refill": True, "network_key": network_key, **report}


def maybe_queue_post_refill_after_scheduled_send(
    db: Session,
    *,
    post: ScheduledTextPost,
    media_items: list[Media],
) -> dict[str, Any]:
    if not media_items:
        return {"ok": True, "skipped": True, "reason": "no_media"}
    pool_id = getattr(media_items[0], "pool_id", None)
    if not pool_id:
        return {"ok": True, "skipped": True, "reason": "no_pool"}
    name = (getattr(post, "name", None) or "").lower()
    if not (
        is_network_tease_scheduler(post)
        or any(nc.scheduler_name.lower() in name for nc in AOF_NETWORK_CHANNELS)
    ):
        return {"ok": True, "skipped": True, "reason": "not_refill_eligible"}
    return maybe_queue_post_refill(db, pool_id=int(pool_id))
