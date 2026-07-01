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
        if not plan:
            logger.warning("Plan %s not found", plan_id)
            return

        from app.services.aof_vip_fulfillment import fulfillment_channel_identifier

        channel_ident = fulfillment_channel_identifier(db, plan_id)
        if not channel_ident and plan.channel_id:
            channel = db.query(Channel).filter(Channel.id == plan.channel_id).first()
            channel_ident = channel.identifier if channel else None
        if not channel_ident:
            logger.warning("No fulfillment channel for plan %s", plan_id)
            return

        add_user_sync(telegram_user_id, channel_ident)
    finally:
        db.close()
