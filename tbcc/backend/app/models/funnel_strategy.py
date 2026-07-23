"""Funnel placement / conversion strategy playbook entries."""

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text

from .base import Base


class FunnelStrategyEntry(Base):
    __tablename__ = "funnel_strategy_entries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(256), nullable=True)
    pattern = Column(String(64), nullable=False)
    surface = Column(String(32), nullable=False)
    copy_template = Column(Text, nullable=True)
    visual_notes = Column(Text, nullable=True)
    screenshot_ref = Column(String(512), nullable=True)
    risk_tags = Column(String(256), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    embedding_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
