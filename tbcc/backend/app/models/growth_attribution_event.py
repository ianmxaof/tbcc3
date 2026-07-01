"""Loot/sub/referral conversions with ambient growth context for closed-loop analytics."""

from datetime import datetime

from sqlalchemy import BigInteger, Column, DateTime, Integer, String, Text

from .base import Base


class GrowthAttributionEvent(Base):
    __tablename__ = "growth_attribution_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    event_type = Column(String(32), nullable=False)
    telegram_user_id = Column(BigInteger, nullable=True)
    amount_stars = Column(Integer, nullable=True)
    plan_id = Column(Integer, nullable=True)
    channel_id = Column(Integer, nullable=True)
    scheduled_post_id = Column(Integer, nullable=True)
    delivery_metric_id = Column(Integer, nullable=True)
    caption_slot_index = Column(Integer, nullable=True)
    posted_hour_local = Column(Integer, nullable=True)
    context_json = Column(Text, nullable=True)
