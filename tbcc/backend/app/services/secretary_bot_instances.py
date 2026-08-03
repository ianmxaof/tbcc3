"""Registry helpers for multi-token secretary clones (Phase 2 topology).

Inbound-only: each active token is a BotFather skin deep-linked from ads/channels.
Shared brain = same Format Engine / RAG / sales coach / reply_mode CRM.
Full multi-app host wiring lands in a follow-up; this module is the durable store.
"""

from __future__ import annotations

import os
from typing import Any

from sqlalchemy.orm import Session

from app.models.secretary_bot_instance import SecretaryBotInstance


def mask_bot_token(token: str | None) -> str:
    raw = (token or "").strip()
    if not raw:
        return ""
    if len(raw) <= 10:
        return "***"
    return f"{raw[:6]}…{raw[-4:]}"


def primary_env_token() -> str:
    return (os.getenv("TBCC_SECRETARY_BOT_TOKEN") or os.getenv("SECRETARY_BOT_TOKEN") or "").strip()


def list_active_instances(db: Session) -> list[SecretaryBotInstance]:
    return (
        db.query(SecretaryBotInstance)
        .filter(SecretaryBotInstance.is_active.is_(True))
        .order_by(SecretaryBotInstance.is_primary.desc(), SecretaryBotInstance.id.asc())
        .all()
    )


def tokens_for_host(db: Session) -> list[dict[str, Any]]:
    """
    Tokens the multi-app host should poll.

    Always includes the env primary token (if set). DB clones append when they have
    a distinct non-empty token.
    """
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    env_tok = primary_env_token()
    if env_tok:
        seen.add(env_tok)
        out.append(
            {
                "source": "env",
                "label": "primary",
                "bot_username": (os.getenv("TBCC_SECRETARY_BOT_USERNAME") or "").strip() or None,
                "bot_token": env_tok,
                "token_masked": mask_bot_token(env_tok),
                "notify_chat_id": None,
                "is_primary": True,
            }
        )
    for row in list_active_instances(db):
        tok = (row.bot_token or "").strip()
        if not tok or tok in seen:
            continue
        seen.add(tok)
        out.append(
            {
                "source": "db",
                "id": row.id,
                "label": row.label or row.bot_username or f"clone-{row.id}",
                "bot_username": row.bot_username,
                "bot_token": tok,
                "token_masked": mask_bot_token(tok),
                "notify_chat_id": row.notify_chat_id,
                "is_primary": bool(row.is_primary),
            }
        )
    return out


def upsert_instance(
    db: Session,
    *,
    bot_token: str,
    bot_username: str | None = None,
    label: str | None = None,
    notify_chat_id: int | None = None,
    is_active: bool = True,
) -> SecretaryBotInstance:
    tok = (bot_token or "").strip()
    if not tok:
        raise ValueError("bot_token required")
    row = (
        db.query(SecretaryBotInstance)
        .filter(SecretaryBotInstance.bot_token == tok)
        .one_or_none()
    )
    if row is None:
        row = SecretaryBotInstance(bot_token=tok)
        db.add(row)
    if bot_username is not None:
        row.bot_username = bot_username.strip().lstrip("@") or None
    if label is not None:
        row.label = label.strip() or None
    if notify_chat_id is not None:
        row.notify_chat_id = int(notify_chat_id)
    row.is_active = bool(is_active)
    db.commit()
    db.refresh(row)
    return row
