"""Loot goblin drops — cap-limited deep-link grants from listening relay."""

from __future__ import annotations

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text

from .base import Base


class GoblinDrop(Base):
    __tablename__ = "goblin_drop"

    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(DateTime, nullable=False)
    token = Column(String(64), nullable=False, unique=True, index=True)
    status = Column(String(16), nullable=False, default="active")  # active | exhausted | revoked
    claims_used = Column(Integer, nullable=False, default=0)
    claims_cap = Column(Integer, nullable=False, default=5)
    relay_log_id = Column(Integer, nullable=True)
    channel_id = Column(Integer, nullable=True)
    message_thread_id = Column(Integer, nullable=True)
    announce_message_id = Column(Integer, nullable=True)
    announced_at = Column(DateTime, nullable=True)
    revoked_at = Column(DateTime, nullable=True)
    extra_json = Column(Text, nullable=True)
