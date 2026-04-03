"""Tracks referred users before they subscribe. Cleared when they subscribe."""
from sqlalchemy import Column, Integer, DateTime

from .base import Base


class ReferralTracking(Base):
    __tablename__ = "referral_tracking"

    id = Column(Integer, primary_key=True, autoincrement=True)
    referred_user_id = Column(Integer, nullable=False)  # Telegram user who clicked ref link
    referrer_user_id = Column(Integer, nullable=False)  # Telegram user who shared the link
    created_at = Column(DateTime, nullable=True)
