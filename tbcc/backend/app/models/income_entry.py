"""Normalized income ledger — internal payments now; external sync later."""

from datetime import datetime

from sqlalchemy import BigInteger, Column, DateTime, Integer, String, Text

from .base import Base


class IncomeEntry(Base):
    __tablename__ = "income_entries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    idempotency_key = Column(String(128), unique=True, nullable=False, index=True)
    source = Column(String(32), nullable=False, index=True)
    source_label = Column(String(256), nullable=True)
    amount_minor = Column(Integer, nullable=False)
    currency = Column(String(8), nullable=False)
    amount_usd_cents = Column(Integer, nullable=False)
    earned_at = Column(DateTime, nullable=True, index=True)
    sync_kind = Column(String(16), nullable=False, default="computed")
    external_ref = Column(String(128), nullable=True)
    subscription_id = Column(Integer, nullable=True)
    telegram_user_id = Column(BigInteger, nullable=True)
    raw_json = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
