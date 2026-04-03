"""Add user to premium channel after successful payment."""
import logging

from app.workers.celery_app import celery
from app.services.channel_access import add_user_sync

logger = logging.getLogger(__name__)


@celery.task(name="app.workers.grant_access_worker.grant_channel_access")
def grant_channel_access(telegram_user_id: int, plan_id: int):
    """Add user to the premium channel linked to the plan."""
    from app.database.session import SessionLocal
    from app.models.subscription_plan import SubscriptionPlan
    from app.models.channel import Channel

    db = SessionLocal()
    try:
        plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.id == plan_id).first()
        if not plan or not plan.channel_id:
            logger.warning("Plan %s not found or has no channel", plan_id)
            return

        channel = db.query(Channel).filter(Channel.id == plan.channel_id).first()
        if not channel:
            logger.warning("Channel %s not found for plan %s", plan.channel_id, plan_id)
            return

        add_user_sync(telegram_user_id, channel.identifier)
    finally:
        db.close()
