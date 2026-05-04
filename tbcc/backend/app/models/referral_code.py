"""Persistent unique referral codes per Telegram user (short ref_* deep links)."""

from sqlalchemy import BigInteger, Column, DateTime, String

from .base import Base


class ReferralCode(Base):
    __tablename__ = "referral_codes"

    telegram_user_id = Column(BigInteger, primary_key=True, autoincrement=False)
    code = Column(String(16), unique=True, nullable=False, index=True)
    created_at = Column(DateTime, nullable=True)
