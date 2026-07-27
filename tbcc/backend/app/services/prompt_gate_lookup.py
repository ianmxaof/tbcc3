"""Resolve provisioned Linkvertise Text slugs for prompt gate keys."""

from __future__ import annotations

import hashlib
import re
from typing import TYPE_CHECKING

from app.models.prompt_gate import PROMPT_GATE_STATUS_PROVISIONED, PromptGate

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

_WS_RE = re.compile(r"[ \t]+")
_BLANK_LINES_RE = re.compile(r"\n{3,}")


def normalize_prompt_body(body: str) -> str:
    """Canonical form for drift detection — stable across minor whitespace edits."""
    raw = (body or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    lines = [_WS_RE.sub(" ", ln.strip()) for ln in raw.split("\n")]
    joined = "\n".join(lines)
    return _BLANK_LINES_RE.sub("\n\n", joined).strip()


def hash_prompt_body(body: str) -> str:
    normalized = normalize_prompt_body(body)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def active_prompt_gate_row(db: Session, key: str) -> PromptGate | None:
    """Latest provisioned row for a stable catalog key."""
    k = (key or "").strip().lower()
    if not k:
        return None
    return (
        db.query(PromptGate)
        .filter(
            PromptGate.key == k,
            PromptGate.status == PROMPT_GATE_STATUS_PROVISIONED,
        )
        .order_by(PromptGate.id.desc())
        .first()
    )


def prompt_gate_url(key: str, db: Session | None = None) -> str | None:
    """
    Return the active Linkvertise slug for a prompt gate key.

    Mirrors ``manual_gate_url(key)`` — optional session opens a short-lived DB read.
    """
    k = (key or "").strip().lower()
    if not k:
        return None

    if db is not None:
        row = active_prompt_gate_row(db, k)
        url = (row.lv_url or "").strip() if row else ""
        return url or None

    from app.database.session import SessionLocal

    session = SessionLocal()
    try:
        row = active_prompt_gate_row(session, k)
        url = (row.lv_url or "").strip() if row else ""
        return url or None
    finally:
        session.close()
