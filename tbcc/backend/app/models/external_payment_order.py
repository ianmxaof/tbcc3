"""Pending external (wallet / manual) payments before admin verification."""

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String

from .base import Base


class ExternalPaymentOrder(Base):
    __tablename__ = "external_payment_orders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    telegram_user_id = Column(Integer, nullable=False, index=True)
    plan_id = Column(Integer, ForeignKey("subscription_plans.id"), nullable=False)
    reference_code = Column(String(32), unique=True, nullable=False, index=True)
    status = Column(String(16), nullable=False, default="pending")  # pending|paid|cancelled
    created_at = Column(DateTime, nullable=True)
    paid_at = Column(DateTime, nullable=True)
