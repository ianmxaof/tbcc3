"""Analytics-driven export flywheel — rank pool media, propose exports, observe/auto execute."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Literal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.data.aof_network import AOF_NETWORK_CHANNELS, network_channel_by_key
from app.data.export_lane_policy import all_lane_policies, lane_policy
from app.models.content_pool import ContentPool
from app.models.media import Media
from app.models.post_delivery_metric import PostDeliveryMetric
from app.services.aof_feed_rhythm_v2 import network_key_for_pool_name
from app.services.content_performance import analytics_timezone, analytics_timezone_label

logger = logging.getLogger(__name__)

FlywheelMode = Literal["observe", "auto"]

REDIS_PROPOSALS = "tbcc:export_flywheel:proposals"
REDIS_DISMISSED = "tbcc:export_flywheel:proposals_dismissed"
REDIS_APPROVED = "tbcc:export_flywheel:proposals_approved"
REDIS_LAST_TICK = "tbcc:export_flywheel:last_tick"
REDIS_DEBOUNCE_PREFIX = "tbcc:export_flywheel:debounce:"


def _redis_client():
    from app.services.content_signals import _redis_client as cs_redis

    return cs_redis()


def flywheel_enabled() -> bool:
    return (os.getenv("TBCC_EXPORT_FLYWHEEL_ENABLED") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def flywheel_mode() -> FlywheelMode:
    raw = (os.getenv("TBCC_EXPORT_FLYWHEEL_MODE") or "observe").strip().lower()
    return "auto" if raw == "auto" else "observe"


def rank_picks_enabled() -> bool:
    return (os.getenv("TBCC_EXPORT_FLYWHEEL_RANK_PICKS") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def browse_intel_rank_enabled() -> bool:
    return (os.getenv("TBCC_EROME_BROWSE_INTEL_RANK") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def tick_minutes() -> int:
    raw = (os.getenv("TBCC_EXPORT_FLYWHEEL_TICK_MINUTES") or "15").strip()
    try:
        return max(5, min(120, int(raw)))
    except ValueError:
        return 15


def daily_cap_per_lane() -> int:
    raw = (os.getenv("TBCC_EXPORT_FLYWHEEL_DAILY_CAP_PER_LANE") or "6").strip()
    try:
        return max(1, min(48, int(raw)))
    except ValueError:
        return 6


def min_views_sample() -> int:
    raw = (os.getenv("TBCC_EXPORT_FLYWHEEL_REQUIRE_MIN_VIEWS_SAMPLE") or "5").strip()
    try:
        return max(0, min(500, int(raw)))
    except ValueError:
        return 5


def network_key_for_pool(db: Session, pool_id: int) -> str | None:
    pool = db.query(ContentPool).filter(ContentPool.id == int(pool_id)).first()
    if not pool:
        return None
    nk = network_key_for_pool_name(pool.name)
    if nk:
        return nk
    for nc in AOF_NETWORK_CHANNELS:
        if nc.pool_name == (pool.name or "").strip():
            return nc.key
    return None


def pool_id_for_network_key(db: Session, network_key: str) -> int | None:
    nk = (network_key or "").strip().lower()
    net = network_channel_by_key(nk)
    if not net:
        return None
    pool = db.query(ContentPool).filter(ContentPool.name == net.pool_name).first()
    return int(pool.id) if pool else None


def approved_pool_depth(db: Session, pool_id: int) -> int:
    return (
        db.query(func.count(Media.id))
        .filter(Media.pool_id == int(pool_id), Media.status == "approved")
        .scalar()
        or 0
    )


def _lane_avg_views(db: Session, network_key: str, *, days: int = 7) -> float:
    since = datetime.utcnow() - timedelta(days=days)
    rows = (
        db.query(PostDeliveryMetric.views_latest)
        .filter(
            PostDeliveryMetric.created_at >= since,
            PostDeliveryMetric.network_key == network_key,
            PostDeliveryMetric.views_latest.isnot(None),
            PostDeliveryMetric.surface.in_(("telegram", None)),
        )
        .all()
    )
    vals = [int(r[0]) for r in rows if r and r[0] is not None]
    return sum(vals) / len(vals) if vals else 0.0


def _media_recency_score(media: Media) -> float:
    created = getattr(media, "created_at", None) or getattr(media, "indexed_at", None)
    if not created:
        return 0.5
    age_h = max(0.0, (datetime.utcnow() - created).total_seconds() / 3600.0)
    return max(0.05, 1.0 / (1.0 + age_h / 48.0))


def _media_performance_score(db: Session, media: Media, network_key: str | None) -> float:
    recency = _media_recency_score(media)
    lane_avg = _lane_avg_views(db, network_key) if network_key else 0.0
    lane_boost = min(1.5, 1.0 + lane_avg / 500.0) if lane_avg else 1.0
    return recency * lane_boost


def _browse_intel_tag_scores() -> dict[str, float]:
    if not browse_intel_rank_enabled():
        return {}
    try:
        from app.services.erome_browse_intel import aggregate_tag_scores, browse_intel_enabled

        if not browse_intel_enabled():
            return {}
        return aggregate_tag_scores()
    except Exception:
        logger.debug("browse intel tag scores skipped", exc_info=True)
        return {}


def _media_browse_intel_boost(media: Media, tag_scores: dict[str, float]) -> float:
    if not tag_scores:
        return 1.0
    try:
        from app.services.erome_browse_intel import media_tag_intel_multiplier

        return media_tag_intel_multiplier(media.tags, tag_scores)
    except Exception:
        return 1.0


def rank_pool_media(
    db: Session,
    pool_id: int,
    limit: int,
    *,
    randomize: bool = False,
) -> list[Media]:
    """Score approved pool rows — recency, lane bias, optional Erome browse-intel tag boost."""
    import random as rnd

    q = db.query(Media).filter(Media.pool_id == int(pool_id), Media.status == "approved")
    rows = q.order_by(Media.id.asc()).limit(500).all()
    from app.services.media_album_dedupe import filter_media_older_than_schedule_min_age

    rows = filter_media_older_than_schedule_min_age(rows)
    if not rows:
        return []
    nk = network_key_for_pool(db, pool_id)
    tag_scores = _browse_intel_tag_scores()
    scored = [
        (m, _media_performance_score(db, m, nk) * _media_browse_intel_boost(m, tag_scores))
        for m in rows
    ]
    if randomize:
        rnd.shuffle(scored)
        scored.sort(key=lambda x: (-x[1], x[0].id))
    else:
        scored.sort(key=lambda x: (-x[1], x[0].id))
    return [m for m, _ in scored[: max(1, int(limit))]]


def exports_last_24h_by_lane(db: Session) -> dict[str, int]:
    since = datetime.utcnow() - timedelta(hours=24)
    rows = (
        db.query(PostDeliveryMetric.network_key, func.count(PostDeliveryMetric.id))
        .filter(
            PostDeliveryMetric.created_at >= since,
            PostDeliveryMetric.surface.in_(("telegram", None)),
            PostDeliveryMetric.network_key.isnot(None),
        )
        .group_by(PostDeliveryMetric.network_key)
        .all()
    )
    return {str(k): int(v) for k, v in rows if k}


def exports_last_24h_by_surface(db: Session) -> dict[str, int]:
    since = datetime.utcnow() - timedelta(hours=24)
    rows = (
        db.query(PostDeliveryMetric.surface, func.count(PostDeliveryMetric.id))
        .filter(PostDeliveryMetric.created_at >= since)
        .group_by(PostDeliveryMetric.surface)
        .all()
    )
    out: dict[str, int] = defaultdict(int)
    for surf, cnt in rows:
        key = (surf or "telegram").strip() or "telegram"
        out[key] += int(cnt)
    return dict(out)


def pool_depth_by_lane(db: Session) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for nk, policy in all_lane_policies().items():
        pid = pool_id_for_network_key(db, nk)
        depth = approved_pool_depth(db, pid) if pid else 0
        out.append(
            {
                "network_key": nk,
                "pool_id": pid,
                "approved_depth": depth,
                "min_depth_policy": policy.min_pool_depth_before_export,
                "backlog_pressure": depth >= policy.min_pool_depth_before_export * 2,
            }
        )
    out.sort(key=lambda x: (-int(x["approved_depth"]), x["network_key"]))
    return out


def _proposal_id(body: dict[str, Any]) -> str:
    core = json.dumps(
        {
            "kind": body.get("kind"),
            "network_key": body.get("network_key"),
            "pool_id": body.get("pool_id"),
            "surfaces": body.get("surfaces"),
            "hour_local": body.get("hour_local"),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(core.encode()).hexdigest()[:12]


def build_export_proposals(db: Session) -> list[dict[str, Any]]:
    """Derive actionable export proposals from lane depth + content_signals export kinds."""
    from app.services.content_signals import compute_strong_signals

    if not flywheel_enabled():
        return []

    report = compute_strong_signals(db)
    proposals: list[dict[str, Any]] = []
    now_local = datetime.now(tz=analytics_timezone())
    hour_local = now_local.hour

    for signal in report.get("signals") or []:
        st = signal.get("signal_type")
        nk = signal.get("network_key")
        if st == "boost_lane_export" and nk:
            pid = pool_id_for_network_key(db, nk)
            policy = lane_policy(nk)
            depth = approved_pool_depth(db, pid) if pid else 0
            if depth < policy.min_pool_depth_before_export:
                continue
            body = {
                "kind": "boost_lane_export",
                "network_key": nk,
                "pool_id": pid,
                "media_ids": [],
                "surfaces": ["telegram", "erome"],
                "hour_local": hour_local,
                "approved_depth": depth,
                "recommendation": signal.get("recommendation"),
                "confidence": signal.get("confidence"),
                "strength": signal.get("strength"),
            }
            body["id"] = _proposal_id(body)
            body["status"] = "pending"
            proposals.append(body)
        elif st == "increase_pool_cadence" and nk:
            pid = pool_id_for_network_key(db, nk)
            body = {
                "kind": "increase_pool_cadence",
                "network_key": nk,
                "pool_id": pid,
                "surfaces": ["telegram"],
                "hour_local": hour_local,
                "recommendation": signal.get("recommendation"),
                "confidence": signal.get("confidence"),
                "strength": signal.get("strength"),
            }
            body["id"] = _proposal_id(body)
            body["status"] = "pending"
            proposals.append(body)
        elif st == "export_to_surface" and nk:
            pid = pool_id_for_network_key(db, nk)
            surfaces = signal.get("surfaces") or ["telegram"]
            body = {
                "kind": "export_to_surface",
                "network_key": nk,
                "pool_id": pid,
                "surfaces": surfaces,
                "hour_local": hour_local,
                "recommendation": signal.get("recommendation"),
                "confidence": signal.get("confidence"),
                "strength": signal.get("strength"),
            }
            body["id"] = _proposal_id(body)
            body["status"] = "pending"
            proposals.append(body)

    proposals.sort(key=lambda x: (-float(x.get("strength") or 0), x.get("network_key") or ""))
    return proposals[:12]


def _load_dismissed() -> set[str]:
    try:
        r = _redis_client()
        return set(r.smembers(REDIS_DISMISSED) or [])
    except Exception:
        return set()


def _load_approved() -> set[str]:
    try:
        r = _redis_client()
        return set(r.smembers(REDIS_APPROVED) or [])
    except Exception:
        return set()


def list_export_proposals(db: Session) -> dict[str, Any]:
    proposals = build_export_proposals(db)
    dismissed = _load_dismissed()
    approved = _load_approved()
    pending = [p for p in proposals if p["id"] not in dismissed]
    return {
        "ok": True,
        "mode": flywheel_mode(),
        "enabled": flywheel_enabled(),
        "computed_at": datetime.utcnow().isoformat() + "Z",
        "proposal_count": len(pending),
        "approved_ids": sorted(approved),
        "proposals": pending,
    }


def dismiss_export_proposal(proposal_id: str) -> dict[str, Any]:
    pid = (proposal_id or "").strip()
    if not pid:
        return {"ok": False, "error": "empty proposal id"}
    try:
        r = _redis_client()
        r.sadd(REDIS_DISMISSED, pid)
        return {"ok": True, "id": pid, "dismissed": True}
    except Exception as e:
        return {"ok": False, "id": pid, "error": str(e)}


def approve_export_proposal(proposal_id: str) -> dict[str, Any]:
    pid = (proposal_id or "").strip()
    if not pid:
        return {"ok": False, "error": "empty proposal id"}
    try:
        r = _redis_client()
        r.sadd(REDIS_APPROVED, pid)
        return {"ok": True, "id": pid, "approved": True}
    except Exception as e:
        return {"ok": False, "id": pid, "error": str(e)}


def flywheel_status(db: Session) -> dict[str, Any]:
    depth = pool_depth_by_lane(db)
    return {
        "ok": True,
        "enabled": flywheel_enabled(),
        "mode": flywheel_mode(),
        "rank_picks": rank_picks_enabled(),
        "browse_intel_rank": browse_intel_rank_enabled(),
        "timezone": analytics_timezone_label(),
        "pool_depth_by_lane": depth,
        "exports_last_24h_by_lane": exports_last_24h_by_lane(db),
        "exports_last_24h_by_surface": exports_last_24h_by_surface(db),
        "daily_cap_per_lane": daily_cap_per_lane(),
        "min_views_sample": min_views_sample(),
        "policies": [p for p in __import__("app.data.export_lane_policy", fromlist=["policy_summary"]).policy_summary()],
    }


def enqueue_export_flywheel_tick(network_key: str | None = None, *, countdown: int = 30) -> dict[str, Any]:
    """Debounced deposit-done trigger."""
    if not flywheel_enabled():
        return {"ok": True, "skipped": True, "reason": "disabled"}
    nk = (network_key or "").strip().lower() or "all"
    try:
        r = _redis_client()
        debounce_key = f"{REDIS_DEBOUNCE_PREFIX}{nk}"
        if r.get(debounce_key):
            return {"ok": True, "skipped": True, "reason": "debounced", "network_key": nk}
        r.setex(debounce_key, 120, "1")
    except Exception:
        pass
    from app.workers.export_flywheel_worker import export_flywheel_tick

    try:
        result = export_flywheel_tick.apply_async(kwargs={"network_key": nk if nk != "all" else None}, countdown=countdown)
        return {"ok": True, "task_id": result.id, "network_key": nk, "countdown": countdown}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


def emit_export_intent(
    db: Session,
    *,
    pool_id: int | None,
    network_key: str | None,
    media_ids: list[int],
    export_source: str = "cache_deposit",
) -> None:
    """Lightweight correlation row after SENT CACHE deposit."""
    from app.models.channel import Channel
    from app.services.content_performance import record_post_delivery_metric

    if not pool_id or not media_ids:
        enqueue_export_flywheel_tick(network_key)
        return
    pool = db.query(ContentPool).filter(ContentPool.id == int(pool_id)).first()
    ch = db.query(Channel).filter(Channel.id == pool.channel_id).first() if pool and pool.channel_id else None
    record_post_delivery_metric(
        db,
        outbound_event=None,
        event_type="export_intent",
        channel=ch,
        pool_id=int(pool_id),
        scheduler_name=(pool.name if pool else None),
        media_ids=media_ids,
        network_key=network_key,
        export_source=export_source,
        surface="intent",
    )
    enqueue_export_flywheel_tick(network_key)


def tick_observe(db: Session, *, push_inbox: bool = True) -> dict[str, Any]:
    if not flywheel_enabled():
        return {"ok": True, "enabled": False, "skipped": True}

    proposals_payload = list_export_proposals(db)
    result = {
        "ok": True,
        "mode": flywheel_mode(),
        "status": flywheel_status(db),
        "proposals": proposals_payload,
    }

    if flywheel_mode() == "auto":
        from app.services.export_flywheel_executor import execute_pending_proposals

        result["execution"] = execute_pending_proposals(db, proposals_payload.get("proposals") or [])

    if push_inbox and proposals_payload.get("proposal_count"):
        try:
            from app.services.admin_inbox import push_admin_inbox_event

            lines = []
            for p in (proposals_payload.get("proposals") or [])[:5]:
                lines.append(f"• [{p.get('kind')}] {p.get('network_key')}: {p.get('recommendation', '')[:120]}")
            push_admin_inbox_event(
                category="export_flywheel",
                title="Export flywheel proposals",
                body="\n".join(lines) or "New export proposals ready for review.",
                importance="info",
                instant=False,
                meta={"proposal_count": proposals_payload.get("proposal_count"), "mode": flywheel_mode()},
            )
        except Exception:
            logger.debug("export flywheel inbox push skipped", exc_info=True)

    try:
        r = _redis_client()
        r.set(REDIS_LAST_TICK, json.dumps({"at": time.time(), "mode": flywheel_mode()}))
    except Exception:
        pass

    return result
