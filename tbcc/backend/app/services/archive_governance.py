"""Shared archive + macro source governance helpers."""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.capture_archive_entry import CaptureArchiveEntry
from app.models.macro_search_source_submission import MacroSearchSourceSubmission
from app.services.model_search_engine import new_custom_site_id, validate_custom_source_url

logger = logging.getLogger(__name__)

ARCHIVE_STATUS_APPROVED = "approved"
ARCHIVE_STATUS_PENDING = "pending"
ARCHIVE_STATUS_REJECTED = "rejected"

SUBMISSION_STATUS_PENDING = "pending"
SUBMISSION_STATUS_APPROVED = "approved"
_SUBMISSION_STATUS_REJECTED = "rejected"

_USERNAME_RE = re.compile(r"^[a-zA-Z0-9._-]{2,64}$")


def _normalize_url(raw: str) -> str | None:
    v = (raw or "").strip()
    if v.startswith(("http://", "https://")) and not v.startswith(("blob:", "data:")):
        return v[:4096]
    return None


def _entry_dict(row: CaptureArchiveEntry) -> dict[str, Any]:
    return {
        "id": row.id,
        "kind": row.kind,
        "value": row.value,
        "source": row.source or "",
        "ref": row.ref or "",
        "note": row.note or "",
        "description": getattr(row, "description", None) or "",
        "tags": row.tags or "",
        "origin": row.origin or "",
        "status": getattr(row, "status", None) or ARCHIVE_STATUS_APPROVED,
        "submitted_by": getattr(row, "submitted_by", None) or "",
        "added_at": row.added_at.isoformat() if row.added_at else None,
        "addedAt": int(row.added_at.timestamp() * 1000) if row.added_at else None,
    }


def normalize_archive_status(raw: str | None) -> str:
    s = (raw or ARCHIVE_STATUS_APPROVED).strip().lower()
    if s in (ARCHIVE_STATUS_PENDING, ARCHIVE_STATUS_REJECTED):
        return s
    return ARCHIVE_STATUS_APPROVED


def submission_row_to_dict(row: MacroSearchSourceSubmission) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "url_template": row.url_template,
        "sample_username": row.sample_username or "",
        "sample_search_url": row.sample_search_url or "",
        "status": row.status,
        "submitted_by": row.submitted_by or "",
        "reviewed_by": row.reviewed_by or "",
        "review_note": row.review_note or "",
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None,
    }


def submit_archive_url(
    db: Session,
    *,
    value: str,
    source: str = "telegram",
    ref: str | None = None,
    note: str | None = None,
    tags: str | None = None,
    origin: str = "telegram",
    submitted_by: str | None = None,
    auto_approve: bool = False,
) -> dict[str, Any]:
    norm = _normalize_url(value)
    if not norm:
        return {"ok": False, "error": "invalid_url"}

    status = ARCHIVE_STATUS_APPROVED if auto_approve else ARCHIVE_STATUS_PENDING
    existing = (
        db.query(CaptureArchiveEntry)
        .filter(CaptureArchiveEntry.kind == "url", CaptureArchiveEntry.value == norm)
        .first()
    )
    if existing:
        cur = normalize_archive_status(existing.status)
        if cur == ARCHIVE_STATUS_APPROVED:
            return {"ok": True, "duplicate": True, "entry": _entry_dict(existing), "status": cur}
        if auto_approve:
            existing.status = ARCHIVE_STATUS_APPROVED
            if source:
                existing.source = source[:80]
            if tags:
                existing.tags = tags[:500]
            if note:
                existing.note = note[:400]
            db.commit()
            db.refresh(existing)
            if not (getattr(existing, "description", None) or "").strip():
                try:
                    from app.services.archive_url_enrich import apply_enrich_to_entry

                    apply_enrich_to_entry(existing, fast=True)
                    db.commit()
                    db.refresh(existing)
                except Exception:
                    logger.exception("archive auto-tag on approve existing failed id=%s", existing.id)
            return {
                "ok": True,
                "approved": True,
                "entry": _entry_dict(existing),
                "status": ARCHIVE_STATUS_APPROVED,
            }
        return {"ok": True, "duplicate": True, "entry": _entry_dict(existing), "status": cur}

    row = CaptureArchiveEntry(
        kind="url",
        value=norm,
        source=source[:80] or None,
        ref=ref[:2000] if ref else None,
        note=note[:400] if note else None,
        tags=tags[:500] if tags else None,
        origin=origin[:32] or None,
        status=status,
        submitted_by=submitted_by[:32] if submitted_by else None,
        added_at=datetime.utcnow(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    if status == ARCHIVE_STATUS_APPROVED:
        try:
            from app.services.archive_url_enrich import apply_enrich_to_entry

            apply_enrich_to_entry(row, fast=True)
            db.commit()
            db.refresh(row)
        except Exception:
            logger.exception("archive auto-tag on submit failed id=%s", row.id)
    return {"ok": True, "created": True, "entry": _entry_dict(row), "status": status}


def set_archive_entry_status(
    db: Session,
    entry_id: int,
    status: str,
    *,
    reviewed_by: str | None = None,
    review_note: str | None = None,
) -> dict[str, Any]:
    row = db.query(CaptureArchiveEntry).filter(CaptureArchiveEntry.id == entry_id).first()
    if not row:
        return {"ok": False, "error": "not_found"}
    st = normalize_archive_status(status)
    if st not in (ARCHIVE_STATUS_APPROVED, ARCHIVE_STATUS_REJECTED, ARCHIVE_STATUS_PENDING):
        return {"ok": False, "error": "invalid_status"}
    row.status = st
    if review_note:
        row.note = review_note[:400]
    db.commit()
    if st == ARCHIVE_STATUS_APPROVED and row.kind == "url" and not (getattr(row, "description", None) or "").strip():
        try:
            from app.services.archive_url_enrich import apply_enrich_to_entry

            apply_enrich_to_entry(row, fast=True)
            db.commit()
        except Exception:
            logger.exception("archive auto-tag on approve failed id=%s", row.id)
    db.refresh(row)
    return {"ok": True, "entry": _entry_dict(row), "status": st}


def list_pending_archive_entries(db: Session, *, limit: int = 100) -> list[dict[str, Any]]:
    rows = (
        db.query(CaptureArchiveEntry)
        .filter(CaptureArchiveEntry.status == ARCHIVE_STATUS_PENDING)
        .order_by(CaptureArchiveEntry.added_at.desc())
        .limit(limit)
        .all()
    )
    return [_entry_dict(r) for r in rows]


def create_macro_source_submission(
    db: Session,
    *,
    name: str,
    url_template: str,
    sample_username: str | None = None,
    sample_search_url: str | None = None,
    submitted_by: str | None = None,
) -> dict[str, Any]:
    err = validate_custom_source_url(url_template)
    if err:
        return {"ok": False, "error": err}
    dup = (
        db.query(MacroSearchSourceSubmission)
        .filter(
            MacroSearchSourceSubmission.url_template == url_template,
            MacroSearchSourceSubmission.status == SUBMISSION_STATUS_PENDING,
        )
        .first()
    )
    if dup:
        return {"ok": True, "duplicate": True, "submission": submission_row_to_dict(dup)}
    row = MacroSearchSourceSubmission(
        name=name[:128],
        url_template=url_template[:1024],
        sample_username=(sample_username or "")[:64] or None,
        sample_search_url=(sample_search_url or "")[:2000] or None,
        status=SUBMISSION_STATUS_PENDING,
        submitted_by=(submitted_by or "")[:32] or None,
        created_at=datetime.utcnow(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"ok": True, "created": True, "submission": submission_row_to_dict(row)}


def list_macro_source_submissions(
    db: Session,
    *,
    status: str | None = SUBMISSION_STATUS_PENDING,
    limit: int = 100,
) -> list[dict[str, Any]]:
    q = db.query(MacroSearchSourceSubmission)
    if status:
        q = q.filter(MacroSearchSourceSubmission.status == status)
    rows = q.order_by(MacroSearchSourceSubmission.created_at.desc()).limit(limit).all()
    return [submission_row_to_dict(r) for r in rows]


def approve_macro_source_submission(
    db: Session,
    submission_id: int,
    *,
    reviewed_by: str | None = None,
    review_note: str | None = None,
    patch_custom_sources: Any = None,
) -> dict[str, Any]:
    row = db.query(MacroSearchSourceSubmission).filter(MacroSearchSourceSubmission.id == submission_id).first()
    if not row:
        return {"ok": False, "error": "not_found"}
    if row.status == SUBMISSION_STATUS_APPROVED:
        return {"ok": True, "already_approved": True, "submission": submission_row_to_dict(row)}

    site = {
        "id": new_custom_site_id(),
        "name": row.name,
        "url": row.url_template,
        "category": "macro",
    }
    if patch_custom_sources is not None:
        ok = patch_custom_sources(site, merge=True)
        if not ok:
            return {"ok": False, "error": "patch_sources_failed"}

    row.status = SUBMISSION_STATUS_APPROVED
    row.reviewed_by = (reviewed_by or "")[:32] or None
    row.review_note = (review_note or "")[:400] or None
    row.reviewed_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return {"ok": True, "submission": submission_row_to_dict(row), "site": site}


def reject_macro_source_submission(
    db: Session,
    submission_id: int,
    *,
    reviewed_by: str | None = None,
    review_note: str | None = None,
) -> dict[str, Any]:
    row = db.query(MacroSearchSourceSubmission).filter(MacroSearchSourceSubmission.id == submission_id).first()
    if not row:
        return {"ok": False, "error": "not_found"}
    row.status = _SUBMISSION_STATUS_REJECTED
    row.reviewed_by = (reviewed_by or "")[:32] or None
    row.review_note = (review_note or "")[:400] or None
    row.reviewed_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return {"ok": True, "submission": submission_row_to_dict(row)}


def append_custom_macro_source(db: Session, site: dict[str, str]) -> bool:
    import json

    from app.api.payment_bot_settings import ROW_ID
    from app.models.payment_bot_settings import PaymentBotSettings

    r = db.query(PaymentBotSettings).filter(PaymentBotSettings.id == ROW_ID).first()
    custom: list[dict[str, str]] = []
    if r and r.macro_search_custom_sources_json:
        try:
            custom = json.loads(r.macro_search_custom_sources_json)
        except Exception:
            custom = []
    if not isinstance(custom, list):
        custom = []
    for item in custom:
        if isinstance(item, dict) and item.get("url") == site.get("url"):
            return True
    custom.append(site)
    if not r:
        r = PaymentBotSettings(id=ROW_ID)
        db.add(r)
    r.macro_search_custom_sources_json = json.dumps(custom[:80])
    db.commit()
    return True
