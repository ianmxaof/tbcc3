"""Per-customer Pilot/Auto reply mode for the secretary Format Engine."""

from __future__ import annotations

import os
from typing import Literal

from sqlalchemy.orm import Session

from app.models.secretary_user_context import SecretaryUserContext

ReplyMode = Literal["pilot", "auto"]

VALID_MODES = frozenset({"pilot", "auto"})


def auto_reply_in_business_env() -> bool:
    return os.getenv("TBCC_SECRETARY_AUTO_REPLY", "").strip().lower() in ("1", "true", "yes", "on")


def suggest_for_direct_dms_env() -> bool:
    """Default True — non-admin direct DMs use draft→approve (pilot)."""
    raw = (os.getenv("TBCC_SECRETARY_SUGGEST_DIRECT") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def inherit_reply_mode(*, is_business: bool) -> ReplyMode:
    """Global env defaults when row.reply_mode is unset."""
    if is_business:
        return "auto" if auto_reply_in_business_env() else "pilot"
    return "pilot" if suggest_for_direct_dms_env() else "auto"


def get_stored_reply_mode(db: Session, telegram_user_id: int) -> ReplyMode | None:
    row = (
        db.query(SecretaryUserContext)
        .filter(SecretaryUserContext.telegram_user_id == int(telegram_user_id))
        .one_or_none()
    )
    if not row:
        return None
    mode = (row.reply_mode or "").strip().lower()
    if mode in VALID_MODES:
        return mode  # type: ignore[return-value]
    return None


def get_reply_mode(db: Session, telegram_user_id: int, *, is_business: bool) -> ReplyMode:
    stored = get_stored_reply_mode(db, telegram_user_id)
    if stored is not None:
        return stored
    return inherit_reply_mode(is_business=is_business)


def set_reply_mode(db: Session, telegram_user_id: int, mode: str) -> ReplyMode:
    cleaned = (mode or "").strip().lower()
    if cleaned not in VALID_MODES:
        raise ValueError(f"reply_mode must be pilot or auto, got {mode!r}")
    row = (
        db.query(SecretaryUserContext)
        .filter(SecretaryUserContext.telegram_user_id == int(telegram_user_id))
        .one_or_none()
    )
    if row is None:
        row = SecretaryUserContext(telegram_user_id=int(telegram_user_id))
        db.add(row)
    row.reply_mode = cleaned
    db.commit()
    return cleaned  # type: ignore[return-value]


def mode_label(mode: ReplyMode | str) -> str:
    return "Pilot" if str(mode).lower() == "pilot" else "Auto"
