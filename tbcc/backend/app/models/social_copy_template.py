"""Rotating social copy templates for Buffer X / IG / Telegram."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text

from .base import Base


class SocialCopyTemplate(Base):
    __tablename__ = "social_copy_templates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    category = Column(String(64), nullable=False, index=True)
    surface = Column(String(32), nullable=False, default="x_buffer", index=True)
    body = Column(Text, nullable=False)
    image_hint = Column(String(32), nullable=True)
    use_count = Column(Integer, nullable=False, default=0)
    max_uses_before_demote = Column(Integer, nullable=False, default=2)
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    last_used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
