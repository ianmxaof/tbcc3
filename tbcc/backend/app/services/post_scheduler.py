from datetime import datetime
from app.models.scheduled_text_post import ScheduledTextPost
from app.workers.poster_worker import post_scheduled_text
from sqlalchemy.orm import Session


def check_and_schedule(db: Session):
    # Pool auto-posting is intentionally disabled.
    # Pool media should be published through scheduled posts only.

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
