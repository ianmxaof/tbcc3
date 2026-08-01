"""Creator profile links → loot modifier pool (gated review queue)."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models.loot import LootCreatorSubmission, LootModifier
from app.services.loot_creator_platforms import (
    label_from_creator_url,
    normalize_creator_url,
    unsupported_url_message,
)

_CREATOR_RATE_LIMIT_PER_DAY = 3
_CREATOR_MAX_PENDING_OR_ACTIVE = 5
_HANDLE_RE = __import__("re").compile(r"^[a-zA-Z0-9._\-\s]{2,48}$")


def _creator_source_note(telegram_user_id: int | None) -> str:
    if telegram_user_id:
        return f"creator:tg:{int(telegram_user_id)}"
    return "creator:self-serve"


def _count_recent_creator_submits(db: Session, telegram_user_id: int) -> int:
    since = datetime.utcnow() - timedelta(hours=24)
    return (
        db.query(LootCreatorSubmission)
        .filter(
            LootCreatorSubmission.telegram_user_id == int(telegram_user_id),
            LootCreatorSubmission.created_at >= since,
        )
        .count()
    )


def _count_open_creator_slots(db: Session, telegram_user_id: int) -> int:
    note = f"creator:tg:{int(telegram_user_id)}"
    pending = (
        db.query(LootCreatorSubmission)
        .filter(
            LootCreatorSubmission.telegram_user_id == int(telegram_user_id),
            LootCreatorSubmission.status == "pending",
        )
        .count()
    )
    active = (
        db.query(LootModifier)
        .filter(
            LootModifier.source_note.like(f"{note}%"),
            LootModifier.active.is_(True),
        )
        .count()
    )
    return pending + active


def _serialize_submission(row: LootCreatorSubmission) -> dict:
    return {
        "submission_id": int(row.id),
        "telegram_user_id": int(row.telegram_user_id),
        "submitted_url": row.submitted_url,
        "normalized_url": row.normalized_url,
        "platform_key": row.platform_key,
        "platform_label": row.platform_label,
        "path_handle": row.path_handle,
        "display_name": row.display_name,
        "label": row.label,
        "status": row.status,
        "review_note": row.review_note,
        "modifier_id": int(row.modifier_id) if row.modifier_id else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def submit_creator_profile(
    db: Session,
    *,
    url: str,
    telegram_user_id: int | None = None,
    display_name: str | None = None,
) -> dict:
    """
    Queue a creator promo for operator review (does not activate modifier until approved).
    """
    parsed = normalize_creator_url(url)
    if not parsed:
        raise ValueError(unsupported_url_message(html=False))

    normalized, platform_key, prefix, path_handle = parsed
    clean_display = (display_name or "").strip() or None
    if clean_display and not _HANDLE_RE.match(clean_display):
        raise ValueError("Display name must be 2–48 characters (letters, numbers, spaces, . _ -).")

    if telegram_user_id:
        uid = int(telegram_user_id)
        if _count_recent_creator_submits(db, uid) >= _CREATOR_RATE_LIMIT_PER_DAY:
            raise ValueError(
                f"Rate limit: max {_CREATOR_RATE_LIMIT_PER_DAY} creator applications per 24 hours on this account."
            )
        if _count_open_creator_slots(db, uid) >= _CREATOR_MAX_PENDING_OR_ACTIVE:
            raise ValueError(
                f"You already have {_CREATOR_MAX_PENDING_OR_ACTIVE} pending or active promos. "
                "Wait for review or ask admin to retire an old one."
            )

    dup_pending = (
        db.query(LootCreatorSubmission)
        .filter(
            LootCreatorSubmission.normalized_url == normalized,
            LootCreatorSubmission.status == "pending",
        )
        .first()
    )
    if dup_pending:
        if telegram_user_id and int(dup_pending.telegram_user_id) == int(telegram_user_id):
            return {
                "ok": True,
                "already_registered": True,
                "pending_review": True,
                "submission_id": int(dup_pending.id),
                "label": dup_pending.label,
                "target_url": dup_pending.normalized_url,
                "message": "That link is already in your review queue.",
            }
        raise ValueError("That profile link is already awaiting review.")

    existing = (
        db.query(LootModifier)
        .filter(
            LootModifier.target_url == normalized,
            LootModifier.active.is_(True),
        )
        .first()
    )
    if existing:
        if telegram_user_id and f"creator:tg:{int(telegram_user_id)}" in (existing.source_note or ""):
            return {
                "ok": True,
                "already_registered": True,
                "pending_review": False,
                "modifier_id": int(existing.id),
                "label": existing.label,
                "target_url": existing.target_url,
                "message": "That link is already live in your active promo pool.",
            }
        raise ValueError("That profile link is already in the loot modifier pool.")

    label = label_from_creator_url(prefix, path_handle, clean_display)
    row = LootCreatorSubmission(
        telegram_user_id=int(telegram_user_id or 0),
        submitted_url=(url or "").strip()[:2048],
        normalized_url=normalized,
        platform_key=platform_key,
        platform_label=prefix,
        path_handle=path_handle,
        display_name=clean_display,
        label=label,
        status="pending",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {
        "ok": True,
        "pending_review": True,
        "submission_id": int(row.id),
        "label": row.label,
        "target_url": row.normalized_url,
        "platform_key": platform_key,
        "message": (
            "Submitted for review — an operator will approve it before it goes live "
            "in the tier 5+ modifier pool."
        ),
    }


def list_creator_submissions(
    db: Session,
    *,
    status: str | None = "pending",
    limit: int = 50,
) -> list[dict]:
    q = db.query(LootCreatorSubmission).order_by(LootCreatorSubmission.id.desc())
    if status:
        q = q.filter(LootCreatorSubmission.status == status)
    rows = q.limit(max(1, min(limit, 200))).all()
    return [_serialize_submission(r) for r in rows]


def approve_creator_submission(
    db: Session,
    submission_id: int,
    *,
    reviewer_user_id: int | None = None,
    review_note: str | None = None,
) -> dict:
    row = db.query(LootCreatorSubmission).filter(LootCreatorSubmission.id == int(submission_id)).first()
    if not row:
        raise ValueError("Submission not found.")
    if row.status != "pending":
        raise ValueError(f"Submission is already {row.status}.")

    existing = (
        db.query(LootModifier)
        .filter(
            LootModifier.target_url == row.normalized_url,
            LootModifier.active.is_(True),
        )
        .first()
    )
    if existing:
        row.status = "approved"
        row.modifier_id = int(existing.id)
        row.reviewed_at = datetime.utcnow()
        row.reviewed_by = int(reviewer_user_id) if reviewer_user_id else None
        row.review_note = (review_note or "Linked to existing active modifier.").strip() or None
        db.commit()
        return {
            "ok": True,
            "submission_id": int(row.id),
            "modifier_id": int(existing.id),
            "message": "Linked to existing modifier.",
        }

    note = _creator_source_note(row.telegram_user_id if row.telegram_user_id else None)
    m = LootModifier(
        kind="internal_route",
        label=row.label,
        target_url=row.normalized_url,
        weight_base=1.0,
        rarity_focus=5.0,
        min_rarity_tier=5,
        bypass_vip=False,
        active=True,
        source_note=note,
    )
    db.add(m)
    db.flush()
    row.status = "approved"
    row.modifier_id = int(m.id)
    row.reviewed_at = datetime.utcnow()
    row.reviewed_by = int(reviewer_user_id) if reviewer_user_id else None
    row.review_note = (review_note or "").strip() or None
    db.commit()
    db.refresh(row)
    return {
        "ok": True,
        "submission_id": int(row.id),
        "modifier_id": int(m.id),
        "label": m.label,
        "target_url": m.target_url,
        "message": "Approved — modifier is live on tier 5+ rolls.",
    }


def reject_creator_submission(
    db: Session,
    submission_id: int,
    *,
    reviewer_user_id: int | None = None,
    review_note: str | None = None,
) -> dict:
    row = db.query(LootCreatorSubmission).filter(LootCreatorSubmission.id == int(submission_id)).first()
    if not row:
        raise ValueError("Submission not found.")
    if row.status != "pending":
        raise ValueError(f"Submission is already {row.status}.")
    row.status = "rejected"
    row.reviewed_at = datetime.utcnow()
    row.reviewed_by = int(reviewer_user_id) if reviewer_user_id else None
    row.review_note = (review_note or "Rejected by operator.").strip() or None
    db.commit()
    return {
        "ok": True,
        "submission_id": int(row.id),
        "message": "Submission rejected.",
    }
