"""Counts for subscription analytics (excludes one-time bundle purchases)."""

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.subscription import Subscription
from app.models.subscription_plan import SubscriptionPlan


def active_subscription_subscriber_count(db: Session) -> int:
    """Distinct users with an active row tied to a *subscription* product (not bundle)."""
    return (
        db.query(func.count(func.distinct(Subscription.telegram_user_id)))
        .join(SubscriptionPlan, Subscription.plan_id == SubscriptionPlan.id)
        .filter(
            Subscription.status == "active",
            SubscriptionPlan.product_type == "subscription",
        )
        .scalar()
        or 0
    )
