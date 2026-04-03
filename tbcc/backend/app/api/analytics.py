"""Basic analytics for subscriptions and revenue."""
from sqlalchemy import func
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.subscription import Subscription
from app.models.subscription_plan import SubscriptionPlan

router = APIRouter()


@router.get("/subscriptions")
def subscription_analytics(db: Session = Depends(get_db)):
    """Return subscription counts and revenue (Stars)."""
    total = db.query(Subscription).count()
    active = db.query(Subscription).filter(Subscription.status == "active").count()
    expired = db.query(Subscription).filter(Subscription.status == "expired").count()
    cancelled = db.query(Subscription).filter(Subscription.status == "cancelled").count()

    # Revenue: sum of amount_stars, fallback to plan.price_stars for legacy rows
    revenue_result = (
        db.query(func.coalesce(func.sum(Subscription.amount_stars), 0))
        .filter(Subscription.status.in_(["active", "expired"]))
        .scalar()
    )
    revenue_stars = int(revenue_result or 0)

    # For rows without amount_stars, add plan price (legacy data)
    legacy_subs = (
        db.query(SubscriptionPlan.price_stars)
        .join(Subscription, Subscription.plan_id == SubscriptionPlan.id)
        .filter(
            Subscription.status.in_(["active", "expired"]),
            Subscription.amount_stars.is_(None),
        )
        .all()
    )
    legacy_revenue = sum((p[0] or 0) for p in legacy_subs)
    revenue_stars += legacy_revenue

    return {
        "total_subscriptions": total,
        "active": active,
        "expired": expired,
        "cancelled": cancelled,
        "revenue_stars": revenue_stars,
    }
