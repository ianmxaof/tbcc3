import os
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.channel import Channel
from app.models.content_pool import ContentPool
from app.models.scheduled_text_post import ScheduledTextPost
from app.workers.poster_worker import post_pool, post_scheduled_text


def pool_auto_post_enabled() -> bool:
    """Pool interval cron via Beat → check_and_schedule. Set TBCC_POOL_AUTO_POST=0 to disable."""
    return (os.getenv("TBCC_POOL_AUTO_POST") or "1").strip().lower() in ("1", "true", "yes", "on")


def _dedupe_campaign_leaders(posts: list[ScheduledTextPost]) -> list[ScheduledTextPost]:
    """Enqueue one Celery task per multi-channel campaign (lowest row id); keep every non-campaign post."""
    seen: set[str] = set()
    out: list[ScheduledTextPost] = []
    for p in sorted(posts, key=lambda x: x.id):
        cg = getattr(p, "campaign_group_id", None)
        if not cg:
            out.append(p)
            continue
        if cg in seen:
            continue
        seen.add(cg)
        out.append(p)
    return out


def _schedule_pool_interval_posts(db: Session, now: datetime) -> None:
    if not pool_auto_post_enabled():
        return
    pools = db.query(ContentPool).all()
    for pool in pools:
        if getattr(pool, "auto_post_enabled", True) is False:
            continue
        channel = (
            db.query(Channel).filter(Channel.id == pool.channel_id).first()
            if pool.channel_id
            else None
        )
        if not channel:
            continue
        interval = max(1, int(pool.interval_minutes or 60))
        if pool.last_posted is None:
            should_post = True
        else:
            minutes_since = (now - pool.last_posted).total_seconds() / 60
            should_post = minutes_since >= interval
        if should_post:
            post_pool.delay(pool.id, channel.identifier)
            pool.last_posted = now


def check_and_schedule(db: Session):
    now = datetime.utcnow()
    _schedule_pool_interval_posts(db, now)

    # Scheduled posts: one-time (scheduled_at <= now, not sent) or recurring (interval elapsed)
    one_time_due = (
        db.query(ScheduledTextPost)
        .filter(
            ScheduledTextPost.interval_minutes.is_(None),
            ScheduledTextPost.sent_at.is_(None),
            ScheduledTextPost.scheduled_at.isnot(None),
            ScheduledTextPost.scheduled_at <= now,
            ScheduledTextPost.posting_auto_paused_at.is_(None),
        )
        .all()
    )
    for post in _dedupe_campaign_leaders(one_time_due):
        post_scheduled_text.delay(post.id)

    recurring = (
        db.query(ScheduledTextPost)
        .filter(
            ScheduledTextPost.interval_minutes.isnot(None),
            ScheduledTextPost.posting_auto_paused_at.is_(None),
        )
        .all()
    )
    recurring_due = []
    for post in recurring:
        if post.last_posted_at is None:
            # First run: API clears scheduled_at for interval jobs, so nothing else selects these rows.
            recurring_due.append(post)
            continue
        if (now - post.last_posted_at).total_seconds() / 60 >= post.interval_minutes:
            recurring_due.append(post)
    for post in _dedupe_campaign_leaders(recurring_due):
        post_scheduled_text.delay(post.id)

    db.commit()
