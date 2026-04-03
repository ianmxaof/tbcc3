"""Persistent unique referral codes per Telegram user (short ref_* deep links)."""

from sqlalchemy import Column, DateTime, Integer, String

from .base import Base


class ReferralCode(Base):
    __tablename__ = "referral_codes"

    telegram_user_id = Column(Integer, primary_key=True, autoincrement=False)
    code = Column(String(16), unique=True, nullable=False, index=True)
    created_at = Column(DateTime, nullable=True)
