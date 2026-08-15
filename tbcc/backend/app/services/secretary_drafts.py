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
import re
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.models.secretary_pending_draft import SecretaryPendingDraft

logger = logging.getLogger(__name__)

DRAFT_TTL_HOURS = 48
CANDIDATE_KEYS = ("natural", "clear", "close")
CANDIDATE_MAX_CHARS = 280
VARIANT_ALIASES = {
    "n": "natural",
    "natural": "natural",
    "k": "clear",
    "c": "clear",
    "clear": "clear",
    "x": "close",
    "z": "close",
    "close": "close",
}

TRIAGE_JSON_INSTRUCTION = (
    "Reply with JSON only (no markdown): "
    '{"natural":"...","clear":"...","close":"..."}. '
    "natural = warm human DM, like a real person typing. "
    "clear = plain facts, no fluff. "
    "close = one next step toward checkout (payment bot) without pressure. "
    "Each value: at most two short sentences and at most 280 characters. "
    "No bullet lists, no numbered steps, no 'I'd be happy to help'."
)


def clamp_candidate(text: str, *, max_chars: int = CANDIDATE_MAX_CHARS) -> str:
    """At most two sentences, then hard-cap characters (blueprint anti-verbosity)."""
    raw = re.sub(r"\s+", " ", (text or "").strip())
    if not raw:
        return ""
    parts = re.split(r"(?<=[.!?])\s+", raw)
    clipped = " ".join(p for p in parts[:2] if p).strip()
    if len(clipped) <= max_chars:
        return clipped
    return clipped[: max_chars - 1].rstrip() + "…"


def parse_triage_candidates(raw: str) -> dict[str, str]:
    """Parse LLM JSON triad; on failure all keys get the clamped raw text."""
    blob = (raw or "").strip()
    parsed: dict[str, Any] | None = None
    if blob:
        try:
            parsed = json.loads(blob)
        except (TypeError, ValueError):
            m = re.search(r"\{.*\}", blob, flags=re.DOTALL)
            if m:
                try:
                    parsed = json.loads(m.group(0))
                except (TypeError, ValueError):
                    parsed = None
    out: dict[str, str] = {}
    if isinstance(parsed, dict):
        for key in CANDIDATE_KEYS:
            out[key] = clamp_candidate(str(parsed.get(key) or ""))
    if not any(out.values()):
        fallback = clamp_candidate(blob)
        return {k: fallback for k in CANDIDATE_KEYS}
    for key in CANDIDATE_KEYS:
        if not out.get(key):
            out[key] = out.get("natural") or next((out[k] for k in CANDIDATE_KEYS if out.get(k)), "")
    return out


def resolve_variant(token: str | None) -> str:
    key = (token or "natural").strip().lower()
    return VARIANT_ALIASES.get(key, "natural")


def pick_candidate(item: dict[str, Any], variant: str | None) -> str:
    resolved = resolve_variant(variant)
    cands = item.get("candidates") if isinstance(item.get("candidates"), dict) else {}
    text = str((cands or {}).get(resolved) or item.get("reply") or "").strip()
    return clamp_candidate(text)


def append_triage_instruction(suffix: str) -> str:
    base = (suffix or "").strip()
    if TRIAGE_JSON_INSTRUCTION in base:
        return base
    if base:
        return base + "\n\n" + TRIAGE_JSON_INSTRUCTION
    return TRIAGE_JSON_INSTRUCTION


def _load_candidates(raw: str | None) -> dict[str, str]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {k: str(data.get(k) or "") for k in CANDIDATE_KEYS}


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
        "candidates": _load_candidates(row.candidates_json),
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
    candidates: dict[str, str] | None = None,
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
    if candidates:
        row.candidates_json = json.dumps(candidates, ensure_ascii=False)
    row.coach_hint = coach_hint
    row.reply_mode = reply_mode
    db.commit()
    db.refresh(row)
    return _row_to_dict(row)


def update_draft_reply(
    db: Session,
    draft_id: str,
    reply: str,
    *,
    candidates: dict[str, str] | None = None,
) -> dict[str, Any] | None:
    """Redo: overwrite reply (and optional triad) — keeps original suffix/messages/created_at."""
    _prune_expired(db)
    row = db.query(SecretaryPendingDraft).filter(SecretaryPendingDraft.draft_id == draft_id).one_or_none()
    if row is None:
        return None
    row.reply_text = reply
    if candidates:
        row.candidates_json = json.dumps(candidates, ensure_ascii=False)
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
        combined = stored + "\n\n" + style_hint
    else:
        combined = style_hint
    return append_triage_instruction(combined)


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
