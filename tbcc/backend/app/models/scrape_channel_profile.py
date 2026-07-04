"""Telegram inbound channel intel — forward policy, AOF mapping, posting cadence."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, Column, DateTime, Float, Integer, String, Text

from .base import Base


class ScrapeChannelProfile(Base):
    __tablename__ = "scrape_channel_profiles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    chat_id = Column(BigInteger, unique=True, nullable=False, index=True)
    source_id = Column(Integer, nullable=True, index=True)
    title = Column(String(512), nullable=True)
    username = Column(String(128), nullable=True)
    identifier = Column(String(256), nullable=True)

    forward_enabled = Column(Boolean, nullable=True)
    forward_probe_at = Column(DateTime, nullable=True)
    skip_reason = Column(String(256), nullable=True)

    pool_key = Column(String(32), nullable=True)
    pool_name = Column(String(128), nullable=True)
    category = Column(String(64), nullable=True)
    folder_label = Column(String(128), nullable=True)
    tags_sample = Column(Text, nullable=True)

    posts_per_day = Column(Float, nullable=True)
    posts_per_week = Column(Float, nullable=True)
    posts_per_month = Column(Float, nullable=True)
    messages_sampled = Column(Integer, nullable=False, default=0)
    last_post_at = Column(DateTime, nullable=True)
    cadence_span_days = Column(Float, nullable=True)
    cadence_json = Column(Text, nullable=True)

    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
