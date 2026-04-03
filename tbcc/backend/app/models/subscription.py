from sqlalchemy import Column, Integer, String, DateTime, ForeignKey

from .base import Base


class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    telegram_user_id = Column(Integer, nullable=False)
    plan_id = Column(Integer, ForeignKey("subscription_plans.id"), nullable=True)
    plan = Column(String, nullable=True)  # denormalized plan name for display
    status = Column(String, default="active")  # active|expired|cancelled
    expires_at = Column(DateTime, nullable=True)
    payment_method = Column(String, nullable=True)  # stars|crypto|manual
    amount_stars = Column(Integer, nullable=True)  # Stars paid at purchase (for analytics)
    referrer_id = Column(Integer, nullable=True)  # Telegram user who referred this subscriber
    # Idempotent Stars fulfillment — duplicate successful_payment webhooks return same row
    telegram_payment_charge_id = Column(String(128), nullable=True, unique=True)
