"""Milestone collective rewards: extend all active subs + broadcast when threshold hit."""
import logging
import os

import httpx

from app.workers.celery_app import celery

logger = logging.getLogger(__name__)


@celery.task(name="app.workers.milestone_worker.process_milestone")
def process_milestone(milestone_id: int, threshold: int, reward_days: int):
    """Extend all active subscriptions by reward_days and broadcast to each subscriber."""
    from app.database.session import SessionLocal
    from app.models.subscription import Subscription
    from app.models.subscription_plan import SubscriptionPlan
    from app.models.subscription_milestone import SubscriptionMilestone
    from datetime import datetime, timedelta

    db = SessionLocal()
    try:
        milestone = db.query(SubscriptionMilestone).filter(SubscriptionMilestone.id == milestone_id).first()
        if not milestone or milestone.triggered_at:
            return

        # Extend all active *subscription* products (not one-time bundles)
        active = (
            db.query(Subscription)
            .join(SubscriptionPlan, Subscription.plan_id == SubscriptionPlan.id)
            .filter(
                Subscription.status == "active",
                Subscription.expires_at.isnot(None),
                SubscriptionPlan.product_type == "subscription",
            )
            .all()
        )
        for sub in active:
            sub.expires_at = sub.expires_at + timedelta(days=reward_days)

        milestone.triggered_at = datetime.utcnow()
        db.commit()

        # Broadcast to each subscriber
        token = os.getenv("BOT_TOKEN", "").strip()
        if not token:
            logger.warning("BOT_TOKEN not set, skipping milestone broadcast")
            return

        msg = (
            f"🎉 **Milestone reached!** We hit **{threshold}** subscribers!\n\n"
            f"Everyone gets **{reward_days} days free** added to their subscription. Thank you!"
        )
        url = f"https://api.telegram.org/bot{token}/sendMessage"

        for sub in active:
            try:
                with httpx.Client(timeout=10) as client:
                    r = client.post(
                        url,
                        json={
                            "chat_id": sub.telegram_user_id,
                            "text": msg,
                            "parse_mode": "Markdown",
                        },
                    )
                    if r.status_code != 200:
                        logger.warning("Milestone broadcast to %s failed: %s", sub.telegram_user_id, r.text)
            except Exception as e:
                logger.warning("Milestone broadcast to %s failed: %s", sub.telegram_user_id, e)

        logger.info("Milestone %s hit: extended %s subs by %s days", threshold, len(active), reward_days)
    finally:
        db.close()


@celery.task(name="app.workers.milestone_worker.broadcast_progress")
def broadcast_progress():
    """Broadcast progress bar to configured chat (e.g. group) for FOMO."""
    import os

    from app.database.session import SessionLocal
    from app.services.growth_settings_effective import get_effective_growth_settings

    db = SessionLocal()
    try:
        s = get_effective_growth_settings(db)
    finally:
        db.close()
    chat_id = (s.get("milestone_progress_chat_id") or "").strip()
    if not chat_id:
        return
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        return

    from app.database.session import SessionLocal
    from app.services.growth_promo import milestone_fomo_message

    db = SessionLocal()
    try:
        msg = milestone_fomo_message(db)
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        with httpx.Client(timeout=10) as client:
            client.post(url, json={"chat_id": chat_id, "text": msg})
    finally:
        db.close()
