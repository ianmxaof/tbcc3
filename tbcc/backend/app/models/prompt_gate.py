"""Linkvertise Text asset gates for gated prompt SKUs (Perchance / Card Lab catalog)."""

from __future__ import annotations

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, func

from .base import Base

# Row lifecycle — batch provision resume + supersede chains.
PROMPT_GATE_STATUS_PENDING = "pending"
PROMPT_GATE_STATUS_PROVISIONED = "provisioned"
PROMPT_GATE_STATUS_SUPERSEDED = "superseded"
PROMPT_GATE_STATUS_TAKEDOWN = "takedown"
PROMPT_GATE_STATUS_FAILED = "failed"

PROMPT_GATE_STATUSES = frozenset(
    {
        PROMPT_GATE_STATUS_PENDING,
        PROMPT_GATE_STATUS_PROVISIONED,
        PROMPT_GATE_STATUS_SUPERSEDED,
        PROMPT_GATE_STATUS_TAKEDOWN,
        PROMPT_GATE_STATUS_FAILED,
    }
)

# v1: Telegram-only; forward-compat for a future X carve-out without a global flag flip.
PROMPT_GATE_SURFACE_TELEGRAM_ONLY = "telegram_only"


class PromptGate(Base):
    """One Linkvertise Text slug for a catalog prompt body."""

    __tablename__ = "prompt_gates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String(128), nullable=False, index=True)
    prompt_ref = Column(String(256), nullable=True)
    prompt_body = Column(Text, nullable=True)
    body_hash = Column(String(64), nullable=True)
    lv_url = Column(String(1024), nullable=True)
    lv_asset_id = Column(String(128), nullable=True)
    status = Column(String(32), nullable=False, default=PROMPT_GATE_STATUS_PENDING, index=True)
    tier = Column(String(64), nullable=True)
    surface_policy = Column(
        String(32),
        nullable=False,
        default=PROMPT_GATE_SURFACE_TELEGRAM_ONLY,
    )
    expires_at = Column(DateTime, nullable=True)
    last_probe_at = Column(DateTime, nullable=True)
    last_probe_flags = Column(Text, nullable=True)
    superseded_by_id = Column(Integer, ForeignKey("prompt_gates.id"), nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
