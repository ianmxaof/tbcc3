"""Copy for referral + milestone “growth” messaging (bulletins, API, bot)."""

from sqlalchemy.orm import Session

from app.models.subscription_milestone import SubscriptionMilestone
from app.services.subscription_metrics import active_subscription_subscriber_count


def milestone_fomo_message(db: Session) -> str:
    """
    One paragraph: progress toward next collective milestone.
    Counts **distinct paying subscribers** (active subscription products), not Telegram group members.
    """
    active_count = active_subscription_subscriber_count(db)
    next_m = (
        db.query(SubscriptionMilestone)
        .filter(SubscriptionMilestone.triggered_at.is_(None))
        .order_by(SubscriptionMilestone.threshold.asc())
        .first()
    )
    if not next_m:
        return (
            f"📊 {active_count} active premium subscriber(s) in the bot. "
            f"All collective milestones have been reached — thank you!"
        )
    slots = max(0, next_m.threshold - active_count)
    return (
        f"📊 {active_count}/{next_m.threshold} premium subscribers — "
        f"at {next_m.threshold}, everyone with an active subscription gets +{next_m.reward_days} free days. "
        f"About {slots} more subscriber(s) to go. (Count = paid via bot, not group member total.)"
    )


def milestone_progress_api_dict(db: Session) -> dict:
    """Shape for GET /subscriptions/milestone-progress (slots + message)."""
    active_count = active_subscription_subscriber_count(db)
    next_milestone = (
        db.query(SubscriptionMilestone)
        .filter(SubscriptionMilestone.triggered_at.is_(None))
        .order_by(SubscriptionMilestone.threshold.asc())
        .first()
    )
    msg = milestone_fomo_message(db)
    if not next_milestone:
        return {
            "current": active_count,
            "next_threshold": None,
            "reward_days": None,
            "slots_to_fill": None,
            "message": msg,
        }
    slots = max(0, next_milestone.threshold - active_count)
    return {
        "current": active_count,
        "next_threshold": next_milestone.threshold,
        "reward_days": next_milestone.reward_days,
        "slots_to_fill": slots,
        "message": msg,
    }


def build_aof_landing_bulletin_text(db: Session) -> str:
    """Full text for periodic AOF landing / pinned-topic bulletin."""
    from app.services.growth_settings_effective import get_effective_growth_settings

    s = get_effective_growth_settings(db)
    custom = (s.get("landing_bulletin_intro") or "").strip()
    if custom:
        intro = custom
    else:
        intro = (
            "🔥 AOF — referrals & milestones\n\n"
            "• Referrals: open our bot → tap /referral — your personal link earns you bonus days when friends subscribe.\n"
            "• Milestones: when we hit subscriber targets, everyone with an active subscription gets bonus days.\n"
        )
    milestone = milestone_fomo_message(db)
    bot_user = (s.get("landing_bulletin_bot_username") or "YOUR_BOT").strip().lstrip("@")
    tail = (
        f"\n\n{milestone}\n\n"
        f"→ t.me/{bot_user} — /referral · /shop · /subscribe"
    )
    return intro.rstrip() + tail
