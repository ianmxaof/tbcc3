from datetime import datetime
from app.models.scheduled_text_post import ScheduledTextPost
from app.workers.poster_worker import post_scheduled_text
from sqlalchemy.orm import Session


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
