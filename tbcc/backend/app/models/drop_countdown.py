"""Scheduled lane drop with edit-in-place countdown ticker."""

from datetime import datetime

from sqlalchemy import BigInteger, Column, DateTime, Integer, String, Text

from .base import Base


class DropCountdownSession(Base):
    __tablename__ = "drop_countdown_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=True)

    channel_id = Column(Integer, nullable=False)
    channel_identifier = Column(String(256), nullable=False)
    message_thread_id = Column(Integer, nullable=True)
    lane_key = Column(String(64), nullable=False)
    pool_id = Column(Integer, nullable=True)
    scheduled_post_id = Column(Integer, nullable=True)

    drop_at = Column(DateTime, nullable=False)
    status = Column(String(32), nullable=False, default="scheduled")
    # pending | countdown | dropped | cancelled | failed

    countdown_chat_id = Column(String(64), nullable=True)
    countdown_message_id = Column(BigInteger, nullable=True)
    last_tick_label = Column(String(32), nullable=True)
    error_note = Column(Text, nullable=True)
