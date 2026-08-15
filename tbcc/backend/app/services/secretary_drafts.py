"""DB-backed HITL draft queue for the secretary bot (Pilot mode).

Replaces the old in-memory `_pending_drafts` dict — this table is the sole
source of truth so pending drafts (and the full LLM context that produced
them) survive a secretary container restart. TTL: rows older than
DRAFT_TTL_HOURS are pruned on every read/write so the table doesn't grow
unbounded.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.models.secretary_pending_draft import SecretaryPendingDraft

logger = logging.getLogger(__name__)

DRAFT_TTL_HOURS = 48


def _prune_expired(db: Session) -> None:
    cutoff = datetime.utcnow() - timedelta(hours=DRAFT_TTL_HOURS)
    try:
        db.query(SecretaryPendingDraft).filter(SecretaryPendingDraft.created_at < cutoff).delete(
            synchronize_session=False
        )
        db.commit()
    except Exception as e:
        db.rollback()
        logger.warning("secretary_drafts prune failed: %s", e)


def _row_to_dict(row: SecretaryPendingDraft) -> dict[str, Any]:
    try:
        llm_messages = json.loads(row.llm_messages_json) if row.llm_messages_json else []
    except (TypeError, ValueError):
        llm_messages = []
    return {
        "draft_id": row.draft_id,
        "chat_id": row.chat_id,
        "business_connection_id": row.business_connection_id,
        "user_id": row.user_id,
        "who": row.who,
        "customer_preview": row.customer_preview or "",
        "reply": row.reply_text,
        "llm_messages": llm_messages,
        "extra_system_suffix": row.extra_system_suffix or "",
        "coach_hint": row.coach_hint or "",
        "reply_mode": row.reply_mode,
        "created_at": int(row.created_at.timestamp()) if row.created_at else None,
    }


def save_draft(
    db: Session,
    *,
    draft_id: str,
    chat_id: int,
    business_connection_id: str | None,
    user_id: int,
    who: str,
    customer_preview: str,
    reply: str,
    llm_messages: list[dict[str, str]],
    extra_system_suffix: str,
    coach_hint: str,
    reply_mode: str,
) -> dict[str, Any]:
    """Create (or overwrite) a draft row keyed by draft_id."""
    _prune_expired(db)
    row = db.query(SecretaryPendingDraft).filter(SecretaryPendingDraft.draft_id == draft_id).one_or_none()
    if row is None:
        row = SecretaryPendingDraft(draft_id=draft_id, created_at=datetime.utcnow())
        db.add(row)
    row.chat_id = int(chat_id)
    row.business_connection_id = business_connection_id
    row.user_id = int(user_id)
    row.who = who
    row.customer_preview = customer_preview
    row.reply_text = reply
    row.llm_messages_json = json.dumps(llm_messages, ensure_ascii=False)
    row.extra_system_suffix = extra_system_suffix
    row.coach_hint = coach_hint
    row.reply_mode = reply_mode
    db.commit()
    db.refresh(row)
    return _row_to_dict(row)


def update_draft_reply(db: Session, draft_id: str, reply: str) -> dict[str, Any] | None:
    """Redo: overwrite the reply text only — keeps the original suffix/messages/created_at."""
    _prune_expired(db)
    row = db.query(SecretaryPendingDraft).filter(SecretaryPendingDraft.draft_id == draft_id).one_or_none()
    if row is None:
        return None
    row.reply_text = reply
    db.commit()
    db.refresh(row)
    return _row_to_dict(row)


def get_draft(db: Session, draft_id: str) -> dict[str, Any] | None:
    _prune_expired(db)
    row = db.query(SecretaryPendingDraft).filter(SecretaryPendingDraft.draft_id == draft_id).one_or_none()
    if row is None:
        return None
    return _row_to_dict(row)


def delete_draft(db: Session, draft_id: str) -> bool:
    _prune_expired(db)
    row = db.query(SecretaryPendingDraft).filter(SecretaryPendingDraft.draft_id == draft_id).one_or_none()
    if row is None:
        return False
    db.delete(row)
    db.commit()
    return True


def list_drafts(db: Session, *, limit: int = 20) -> list[dict[str, Any]]:
    _prune_expired(db)
    rows = (
        db.query(SecretaryPendingDraft)
        .order_by(SecretaryPendingDraft.created_at.desc())
        .limit(limit)
        .all()
    )
    return [_row_to_dict(r) for r in reversed(rows)]


def count_drafts(db: Session) -> int:
    """Read-only count of non-expired drafts — does not mutate/prune the caller's session."""
    cutoff = datetime.utcnow() - timedelta(hours=DRAFT_TTL_HOURS)
    return db.query(SecretaryPendingDraft).filter(SecretaryPendingDraft.created_at >= cutoff).count()


def build_redo_suffix(stored_suffix: str, style: str, custom: str = "") -> str:
    """Redo must keep FE + sales-coach + RAG context — never a style-only rewrite (blueprint G5).

    stored_suffix is the FULL suffix used on the first complete_secretary_chat call for this
    draft; style/custom add only the tone instruction on top of it.
    """
    from app.services.secretary_llm import REDO_STYLE_HINTS

    if style == "custom" and custom:
        style_hint = f"Rewrite the assistant reply with this instruction: {custom}"
    else:
        style_hint = REDO_STYLE_HINTS.get(style) or REDO_STYLE_HINTS["pro"]
    stored = (stored_suffix or "").strip()
    if stored:
        return stored + "\n\n" + style_hint
    return style_hint


def suggest_customer_lines(
    prev_lines: list[str],
    db_history: list[dict[str, str]],
) -> list[str]:
    """Pilot/suggest customer-thread lines.

    Prefers live in-memory customer lines (fast path within one process lifetime); falls back
    to Format Engine DB user turns when memory is empty (fresh process / restart — blueprint G6).
    """
    cleaned = [str(x).strip() for x in prev_lines if str(x).strip()]
    if cleaned:
        return cleaned
    return [
        str(m.get("content") or "").strip()
        for m in db_history
        if m.get("role") == "user" and str(m.get("content") or "").strip()
    ]
