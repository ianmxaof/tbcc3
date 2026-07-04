"""Ledger: multi-surface deploy outcomes (Telegram + Buffer + Discord)."""

from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text

from .base import Base


class CampaignDeployEvent(Base):
    __tablename__ = "campaign_deploy_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    scheduled_post_id = Column(Integer, nullable=True)
    campaign_group_id = Column(String(36), nullable=True)
    trigger = Column(String(32), nullable=False, default="api")
    telegram_status = Column(String(16), nullable=False, default="skipped")
    telegram_error = Column(Text, nullable=True)
    buffer_status = Column(String(16), nullable=False, default="skipped")
    buffer_error = Column(Text, nullable=True)
    discord_status = Column(String(16), nullable=False, default="skipped")
    discord_error = Column(Text, nullable=True)
    surfaces_json = Column(Text, nullable=True)
