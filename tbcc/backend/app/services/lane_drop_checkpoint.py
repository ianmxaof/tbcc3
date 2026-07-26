"""Lane Drop Checkpoint — create / list / approve / reject (no auto-post in v1)."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.lane_drop import LaneDrop

STATUS_PENDING = "pending_checkpoint"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"
STATUS_POSTED = "posted_glimpse"


def create_lane_drop(
    db: Session,
    *,
    network_key: str,
    title: str | None = None,
    promo_path: str | None = None,
    lane_path: str | None = None,
    vault_path: str | None = None,
    glimpse_paths: list[str] | None = None,
    destination_url: str | None = None,
    primary_gate_url: str | None = None,
    source_note: str | None = None,
) -> LaneDrop:
    nk = (network_key or "").strip().lower()
    if not nk:
        raise ValueError("network_key required")
    row = LaneDrop(
        network_key=nk,
        status=STATUS_PENDING,
        title=(title or "").strip()[:256] or None,
        promo_path=(promo_path or "").strip() or None,
        lane_path=(lane_path or "").strip() or None,
        vault_path=(vault_path or "").strip() or None,
        glimpse_manifest_json=json.dumps(glimpse_paths) if glimpse_paths else None,
        destination_url=(destination_url or "").strip()[:1024] or None,
        primary_gate_url=(primary_gate_url or "").strip()[:1024] or None,
        source_note=(source_note or "").strip() or None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def list_lane_drops(
    db: Session,
    *,
    status: str | None = STATUS_PENDING,
    network_key: str | None = None,
    limit: int = 50,
) -> list[LaneDrop]:
    q = db.query(LaneDrop)
    if status:
        q = q.filter(LaneDrop.status == status)
    if network_key:
        q = q.filter(LaneDrop.network_key == (network_key or "").strip().lower())
    return q.order_by(LaneDrop.id.desc()).limit(max(1, min(int(limit), 200))).all()


def approve_lane_drop(
    db: Session,
    drop_id: int,
    *,
    review_note: str | None = None,
) -> LaneDrop:
    row = db.query(LaneDrop).filter(LaneDrop.id == int(drop_id)).one_or_none()
    if row is None:
        raise LookupError("lane_drop_not_found")
    if row.status not in (STATUS_PENDING,):
        raise ValueError(f"cannot_approve_status_{row.status}")
    row.status = STATUS_APPROVED
    row.reviewed_at = datetime.utcnow()
    row.review_note = (review_note or "").strip() or None
    db.commit()
    db.refresh(row)
    return row


def reject_lane_drop(
    db: Session,
    drop_id: int,
    *,
    review_note: str | None = None,
) -> LaneDrop:
    row = db.query(LaneDrop).filter(LaneDrop.id == int(drop_id)).one_or_none()
    if row is None:
        raise LookupError("lane_drop_not_found")
    if row.status not in (STATUS_PENDING,):
        raise ValueError(f"cannot_reject_status_{row.status}")
    row.status = STATUS_REJECTED
    row.reviewed_at = datetime.utcnow()
    row.review_note = (review_note or "").strip() or None
    db.commit()
    db.refresh(row)
    return row


def lane_drop_as_dict(row: LaneDrop) -> dict[str, Any]:
    manifest = None
    if row.glimpse_manifest_json:
        try:
            manifest = json.loads(row.glimpse_manifest_json)
        except Exception:
            manifest = None
    return {
        "id": row.id,
        "network_key": row.network_key,
        "status": row.status,
        "title": row.title,
        "promo_path": row.promo_path,
        "lane_path": row.lane_path,
        "vault_path": row.vault_path,
        "glimpse_paths": manifest,
        "destination_url": row.destination_url,
        "primary_gate_url": row.primary_gate_url,
        "source_note": row.source_note,
        "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None,
        "review_note": row.review_note,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }
