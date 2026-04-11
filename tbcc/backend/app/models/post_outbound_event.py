"""Append-only log of outbound Telegram posts (scheduled + pool) for dashboard analytics."""

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text

from .base import Base


class PostOutboundEvent(Base):
    __tablename__ = "post_outbound_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    event_type = Column(String(32), nullable=False)
    channel_id = Column(Integer, nullable=True)
    scheduled_post_id = Column(Integer, nullable=True)
    pool_id = Column(Integer, nullable=True)
    ok = Column(Boolean, nullable=False, default=True)
    error_message = Column(Text, nullable=True)
    extra_json = Column(Text, nullable=True)
