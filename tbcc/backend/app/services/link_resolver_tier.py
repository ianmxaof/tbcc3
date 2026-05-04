"""Resolve link-resolver tier from subscription rows (server-side, do not trust the bot)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.models.subscription import Subscription


def effective_link_resolver_tier(db: Session, telegram_user_id: int) -> str:
    """
    premium: any non-expired active subscription (subscriptions + bundles).
    free: otherwise.
    """
    now = datetime.utcnow()
    rows = (
        db.query(Subscription)
        .filter(
            Subscription.telegram_user_id == telegram_user_id,
            Subscription.status == "active",
        )
        .all()
    )
    for sub in rows:
        exp = sub.expires_at
        if exp is None or exp > now:
            return "premium"
    return "free"
