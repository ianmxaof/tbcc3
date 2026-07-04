"""Resolve link-resolver tier from subscription rows (server-side, do not trust the bot)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.services.subscription_access import effective_link_resolver_tier as _effective_tier


def effective_link_resolver_tier(db: Session, telegram_user_id: int) -> str:
    """
    premium: any non-expired active subscription (subscriptions + bundles).
    free: otherwise.
    """
    return _effective_tier(db, telegram_user_id)
