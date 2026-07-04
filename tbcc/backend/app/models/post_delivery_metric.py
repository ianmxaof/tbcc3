"""Telegram post delivery + view snapshots for content performance analytics."""

from datetime import datetime

from sqlalchemy import BigInteger, Column, DateTime, Integer, String, Text

from .base import Base


class PostDeliveryMetric(Base):
    __tablename__ = "post_delivery_metrics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    post_outbound_event_id = Column(Integer, nullable=True)
    event_type = Column(String(32), nullable=False)
    channel_id = Column(Integer, nullable=True)
    scheduled_post_id = Column(Integer, nullable=True)
    pool_id = Column(Integer, nullable=True)
    scheduler_name = Column(String(256), nullable=True)
    channel_identifier = Column(String(256), nullable=True)
    telegram_message_id = Column(BigInteger, nullable=True)
    telegram_message_ids_json = Column(Text, nullable=True)
    caption_slot_index = Column(Integer, nullable=True)
    caption_variation_count = Column(Integer, nullable=True)
    posted_hour_utc = Column(Integer, nullable=True)
    posted_hour_local = Column(Integer, nullable=True)
    timezone_label = Column(String(64), nullable=True)
    views_latest = Column(Integer, nullable=True)
    views_peak = Column(Integer, nullable=True)
    forwards_latest = Column(Integer, nullable=True)
    views_updated_at = Column(DateTime, nullable=True)
    media_ids_json = Column(Text, nullable=True)
    network_key = Column(String(32), nullable=True)
    export_source = Column(String(32), nullable=True)
    surface = Column(String(32), nullable=True)
    external_post_id = Column(String(512), nullable=True)
