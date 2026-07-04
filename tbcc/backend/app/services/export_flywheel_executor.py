"""Execute export flywheel proposals when mode=auto (or manually approved during observe)."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.data.aof_network import network_channel_by_key
from app.data.export_lane_policy import lane_policy
from app.models.content_pool import ContentPool
from app.models.post_delivery_metric import PostDeliveryMetric
from app.services.export_flywheel_service import (
    _load_approved,
    daily_cap_per_lane,
    flywheel_mode,
    min_views_sample,
    network_key_for_pool,
)

logger = logging.getLogger(__name__)


def pool_buffer_mirror_enabled() -> bool:
    return (os.getenv("TBCC_POOL_BUFFER_MIRROR") or "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def pool_erome_mirror_enabled() -> bool:
    return (os.getenv("TBCC_POOL_EROME_MIRROR") or "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _lane_exports_today(db: Session, network_key: str) -> int:
    since = datetime.utcnow() - timedelta(hours=24)
    return (
        db.query(PostDeliveryMetric)
        .filter(
            PostDeliveryMetric.created_at >= since,
            PostDeliveryMetric.network_key == network_key,
            PostDeliveryMetric.event_type.in_(("pool_album_posted", "scheduled_post_sent", "export_executed")),
            PostDeliveryMetric.surface.in_(("telegram", None)),
        )
        .count()
    )


def _views_sample_ready(db: Session) -> bool:
    need = min_views_sample()
    if need <= 0:
        return True
    count = (
        db.query(PostDeliveryMetric)
        .filter(PostDeliveryMetric.views_latest.isnot(None))
        .count()
    )
    return count >= need


def execute_proposal(db: Session, proposal: dict[str, Any]) -> dict[str, Any]:
    nk = (proposal.get("network_key") or "").strip().lower()
    kind = proposal.get("kind") or "boost_lane_export"
    pool_id = proposal.get("pool_id")
    if not nk or not pool_id:
        return {"ok": False, "error": "missing network_key or pool_id", "proposal_id": proposal.get("id")}

    if _lane_exports_today(db, nk) >= daily_cap_per_lane():
        return {"ok": False, "skipped": True, "reason": "daily_cap", "network_key": nk}

    if flywheel_mode() == "auto" and not _views_sample_ready(db):
        return {"ok": False, "skipped": True, "reason": "insufficient_views_sample", "network_key": nk}

    policy = lane_policy(nk)
    depth = __import__("app.services.export_flywheel_service", fromlist=["approved_pool_depth"]).approved_pool_depth(
        db, int(pool_id)
    )
    if depth < policy.min_pool_depth_before_export:
        return {"ok": False, "skipped": True, "reason": "pool_too_shallow", "network_key": nk, "depth": depth}

    pool = db.query(ContentPool).filter(ContentPool.id == int(pool_id)).first()
    net = network_channel_by_key(nk)
    if not pool or not net:
        return {"ok": False, "error": "pool or network missing", "network_key": nk}

    ch_ident = net.identifier
    actions: list[dict[str, Any]] = []

    if kind in ("boost_lane_export", "export_to_surface", "increase_pool_cadence"):
        from app.workers.poster_worker import post_pool

        task = post_pool.apply_async(args=[int(pool_id), ch_ident])
        actions.append({"action": "post_pool", "task_id": task.id, "pool_id": pool_id, "channel": ch_ident})

    if kind == "increase_pool_cadence" and pool.interval_minutes and pool.interval_minutes > 15:
        old = int(pool.interval_minutes)
        pool.interval_minutes = max(15, old // 2)
        db.commit()
        actions.append({"action": "lower_interval", "from": old, "to": pool.interval_minutes})

    surfaces = proposal.get("surfaces") or ["telegram"]
    if "buffer_x" in surfaces or "buffer" in surfaces:
        actions.append({"action": "buffer_mirror", "note": "pool buffer mirror env-gated on post_pool success"})
    if "erome" in surfaces:
        actions.append({"action": "erome_mirror", "note": "pool erome mirror env-gated on post_pool success"})

    return {
        "ok": True,
        "proposal_id": proposal.get("id"),
        "network_key": nk,
        "kind": kind,
        "actions": actions,
    }


def execute_pending_proposals(db: Session, proposals: list[dict[str, Any]]) -> dict[str, Any]:
    if flywheel_mode() != "auto":
        approved = _load_approved()
        proposals = [p for p in proposals if p.get("id") in approved]
    results = []
    for p in proposals[:3]:
        try:
            results.append(execute_proposal(db, p))
        except Exception as e:
            logger.exception("export proposal execute failed")
            results.append({"ok": False, "proposal_id": p.get("id"), "error": str(e)[:200]})
    return {"ok": True, "executed": len(results), "results": results}


def after_pool_telegram_mirrors(
    db: Session,
    *,
    pool_id: int,
    media_ids: list[int],
    delivery_metric_id: int | None = None,
) -> dict[str, Any]:
    """Optional multi-surface mirrors after pool album post (env-gated)."""
    from app.services.content_performance import latest_telegram_delivery_for_pool, record_surface_delivery_metric

    parent = None
    if delivery_metric_id:
        parent = db.query(PostDeliveryMetric).filter(PostDeliveryMetric.id == int(delivery_metric_id)).first()
    if not parent:
        parent = latest_telegram_delivery_for_pool(db, pool_id)

    out: dict[str, Any] = {"ok": True, "mirrors": []}
    nk = network_key_for_pool(db, pool_id)
    erome_album_url: str | None = None

    if pool_erome_mirror_enabled() and media_ids:
        try:
            from app.services.pool_surface_mirror import mirror_pool_media_to_erome

            er = mirror_pool_media_to_erome(db, pool_id=pool_id, media_ids=media_ids, network_key=nk)
            if er.get("album_url"):
                erome_album_url = str(er["album_url"]).strip()
            if erome_album_url and parent:
                record_surface_delivery_metric(
                    db,
                    parent=parent,
                    surface="erome",
                    external_post_id=erome_album_url,
                    export_source="pool_interval",
                )
                db.commit()
            out["mirrors"].append({"surface": "erome", **er})
        except Exception as e:
            out["mirrors"].append({"surface": "erome", "ok": False, "error": str(e)[:200]})

    if pool_buffer_mirror_enabled() and parent:
        try:
            from app.services.pool_surface_mirror import mirror_pool_delivery_to_buffer

            buf = mirror_pool_delivery_to_buffer(
                db,
                pool_id=pool_id,
                parent=parent,
                network_key=nk,
                erome_album_url=erome_album_url,
            )
            if buf.get("post_id") and parent:
                record_surface_delivery_metric(
                    db,
                    parent=parent,
                    surface="buffer_x",
                    external_post_id=str(buf["post_id"]),
                    export_source="pool_interval",
                )
                db.commit()
            out["mirrors"].append({"surface": "buffer_x", **buf})
        except Exception as e:
            out["mirrors"].append({"surface": "buffer_x", "ok": False, "error": str(e)[:200]})

    return out
