"""Per-user traffic source touch — first/last deep-link attribution."""

from datetime import datetime

from sqlalchemy import BigInteger, Column, DateTime, Integer, String

from .base import Base


class UserFunnelTouch(Base):
    __tablename__ = "user_funnel_touches"

    telegram_user_id = Column(BigInteger, primary_key=True)
    first_source_ref = Column(String(64), nullable=True)
    first_entry_payload = Column(String(128), nullable=True)
    first_seen_at = Column(DateTime, nullable=True)
    last_source_ref = Column(String(64), nullable=True)
    last_entry_payload = Column(String(128), nullable=True)
    last_seen_at = Column(DateTime, nullable=True)
    touch_count = Column(Integer, nullable=False, default=0)
