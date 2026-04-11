from datetime import datetime
from app.models.content_pool import ContentPool
from app.models.channel import Channel
from app.models.scheduled_text_post import ScheduledTextPost
from app.workers.poster_worker import post_pool, post_scheduled_text
from sqlalchemy.orm import Session


def check_and_schedule(db: Session):
    pools = db.query(ContentPool).all()
    now = datetime.utcnow()

    for pool in pools:
        channel = db.query(Channel).filter(Channel.id == pool.channel_id).first() if pool.channel_id else None
        if not channel:
            continue
        if pool.last_posted is None:
            should_post = True
        else:
            minutes_since = (now - pool.last_posted).total_seconds() / 60
            should_post = minutes_since >= pool.interval_minutes

        if should_post:
            post_pool.delay(pool.id, channel.identifier)
            # Advance interval immediately so we do not enqueue duplicate pool jobs every 5 minutes.
            # poster_worker.post_pool overwrites this on success with the actual completion time.
            pool.last_posted = now

    # Process scheduled posts: one-time (scheduled_at <= now, not sent) or recurring (interval elapsed)
    now = datetime.utcnow()
    one_time_due = (
        db.query(ScheduledTextPost)
        .filter(
            ScheduledTextPost.interval_minutes.is_(None),
            ScheduledTextPost.sent_at.is_(None),
            ScheduledTextPost.scheduled_at.isnot(None),
            ScheduledTextPost.scheduled_at <= now,
        )
        .all()
    )
    for post in one_time_due:
        post_scheduled_text.delay(post.id)

    recurring = db.query(ScheduledTextPost).filter(
        ScheduledTextPost.interval_minutes.isnot(None),
        ScheduledTextPost.last_posted_at.isnot(None),
    ).all()
    for post in recurring:
        minutes_since = (now - post.last_posted_at).total_seconds() / 60
        if minutes_since >= post.interval_minutes:
            post_scheduled_text.delay(post.id)

    db.commit()
