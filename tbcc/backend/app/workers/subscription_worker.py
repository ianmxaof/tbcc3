from datetime import datetime

from app.workers.celery_app import celery
from app.database.session import SessionLocal
from app.models.subscription import Subscription
from app.models.subscription_plan import SubscriptionPlan
from app.models.channel import Channel
from app.services.channel_access import remove_user_sync


@celery.task(name="app.workers.subscription_worker.cleanup_expired_subscriptions")
def cleanup_expired_subscriptions():
    """Mark expired subscriptions and remove users from premium channels."""
    db = SessionLocal()
    try:
        expired = (
            db.query(Subscription)
            .filter(
                Subscription.expires_at < datetime.utcnow(),
                Subscription.status == "active",
            )
            .all()
        )
        for sub in expired:
            sub.status = "expired"
            # Remove user from premium channel
            if sub.plan_id:
                plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.id == sub.plan_id).first()
                if plan and plan.channel_id:
                    channel = db.query(Channel).filter(Channel.id == plan.channel_id).first()
                    if channel:
                        remove_user_sync(sub.telegram_user_id, channel.identifier)
        db.commit()
    finally:
        db.close()
