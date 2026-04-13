"""Remove a content pool and dependent rows (media, source links, scheduler pool refs)."""

from sqlalchemy.orm import Session

from app.models.content_pool import ContentPool
from app.models.media import Media
from app.models.scheduled_text_post import ScheduledTextPost
from app.models.source import Source


def cascade_delete_pool(db: Session, pool_id: int) -> bool:
    """Delete pool `pool_id` and clear dependent data. Does not commit. Returns False if pool missing."""
    p = db.query(ContentPool).filter(ContentPool.id == pool_id).first()
    if not p:
        return False
    db.query(Media).filter(Media.pool_id == pool_id).delete(synchronize_session=False)
    db.query(Source).filter(Source.pool_id == pool_id).update({Source.pool_id: None}, synchronize_session=False)
    db.query(ScheduledTextPost).filter(ScheduledTextPost.pool_id == pool_id).update(
        {ScheduledTextPost.pool_id: None}, synchronize_session=False
    )
    db.delete(p)
    return True
