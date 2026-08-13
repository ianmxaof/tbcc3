"""Persistent emotional context + interaction formats for the secretary (Format Engine)."""

from datetime import datetime

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from .base import Base


class SecretaryUserContext(Base):
    """One row per Telegram user — living interaction format + phase state."""

    __tablename__ = "secretary_user_contexts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    telegram_user_id = Column(BigInteger, nullable=False, unique=True, index=True)
    telegram_username = Column(String(128), nullable=True)
    current_phase = Column(String(32), nullable=False, default="introduction")
    interaction_format_json = Column(Text, nullable=True)
    emotional_summary = Column(String(512), nullable=True)
    # Per-customer Pilot/Auto override; NULL = inherit TBCC_SECRETARY_* env defaults.
    reply_mode = Column(String(16), nullable=True)
    message_count = Column(Integer, nullable=False, default=0)
    last_user_at = Column(DateTime, nullable=True)
    last_assistant_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    messages = relationship(
        "SecretaryMessageRecord",
        back_populates="context",
        cascade="all, delete-orphan",
        order_by="SecretaryMessageRecord.created_at",
    )


class SecretaryMessageRecord(Base):
    """Append-only message log with lightweight emotion signals."""

    __tablename__ = "secretary_message_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    context_id = Column(Integer, ForeignKey("secretary_user_contexts.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(16), nullable=False)  # user | assistant
    content = Column(Text, nullable=False)
    emotion_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    context = relationship("SecretaryUserContext", back_populates="messages")
