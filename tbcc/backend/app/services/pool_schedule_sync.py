"""Keep album pick settings aligned between ContentPool and ScheduledTextPost rows."""
from sqlalchemy.orm import Session

from app.models.content_pool import ContentPool
from app.models.scheduled_text_post import ScheduledTextPost


def sync_pool_album_settings_to_schedules(
    db: Session,
    pool_id: int,
    *,
    album_size: int | None = None,
    randomize_queue: bool | None = None,
) -> int:
    """Push pool album_size / randomize_queue to every scheduler job bound to this pool."""
    if album_size is None and randomize_queue is None:
        return 0
    n = 0
    rows = (
        db.query(ScheduledTextPost)
        .filter(
            ScheduledTextPost.pool_id == int(pool_id),
            ScheduledTextPost.pool_collective_random.is_(False),
        )
        .all()
    )
    for post in rows:
        if album_size is not None:
            post.album_size = min(10, max(1, int(album_size)))
        if randomize_queue is not None:
            post.pool_randomize = bool(randomize_queue)
        n += 1
    return n


def sync_schedule_album_settings_to_pool(post: ScheduledTextPost, db: Session) -> bool:
    """Pull a job's album_size / pool_randomize back onto its ContentPool (specific pool only)."""
    if not post.pool_id or bool(getattr(post, "pool_collective_random", False)):
        return False
    pool = db.query(ContentPool).filter(ContentPool.id == int(post.pool_id)).first()
    if not pool:
        return False
    changed = False
    if post.album_size is not None:
        v = min(10, max(1, int(post.album_size)))
        if pool.album_size != v:
            pool.album_size = v
            changed = True
    if post.pool_randomize is not None:
        rv = bool(post.pool_randomize)
        if bool(pool.randomize_queue) != rv:
            pool.randomize_queue = rv
            changed = True
    return changed
