"""Subscription milestones for collective rewards (e.g. 100, 250, 500 subs)."""
from sqlalchemy import Column, Integer, DateTime

from .base import Base


class SubscriptionMilestone(Base):
    __tablename__ = "subscription_milestones"

    id = Column(Integer, primary_key=True, autoincrement=True)
    threshold = Column(Integer, nullable=False)  # e.g. 100, 250, 500
    reward_days = Column(Integer, nullable=False, default=3)  # days to extend each active sub
    triggered_at = Column(DateTime, nullable=True)  # when this milestone was hit
