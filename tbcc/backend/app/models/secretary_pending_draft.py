"""Persisted HITL draft queue for the secretary bot (Pilot mode) — survives restarts."""

from datetime import datetime

from sqlalchemy import BigInteger, Column, DateTime, Integer, String, Text

from .base import Base


class SecretaryPendingDraft(Base):
    """One row per pending Pilot draft card. Canonical store (no in-memory cache)."""

    __tablename__ = "secretary_pending_drafts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    draft_id = Column(String(16), nullable=False, unique=True, index=True)
    chat_id = Column(BigInteger, nullable=False)
    business_connection_id = Column(String(128), nullable=True)
    user_id = Column(BigInteger, nullable=False, index=True)
    who = Column(String(128), nullable=True)
    customer_preview = Column(Text, nullable=True)
    reply_text = Column(Text, nullable=False)
    # JSON-encoded pre-suffix chat messages (system + user) used for the first completion.
    llm_messages_json = Column(Text, nullable=True)
    # Full system suffix (FE + sales coach + RAG + catalog + pilot note) used on the first
    # complete_secretary_chat call — redo reuses this instead of a style-only rewrite.
    extra_system_suffix = Column(Text, nullable=True)
    # JSON {"natural","clear","close"} — Pilot triage set; reply_text is the default (natural).
    candidates_json = Column(Text, nullable=True)
    coach_hint = Column(String(256), nullable=True)
    reply_mode = Column(String(16), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
