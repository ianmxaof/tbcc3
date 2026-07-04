"""Send-time FIFO movie picker + tag-driven caption for AOF FULL LENGTH."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.media import Media
from app.models.scheduled_text_post import ScheduledTextPost
from app.services.aof_full_length_caption import (
    build_movie_body_for_media,
    inject_movie_body,
)
from app.services.aof_full_length_pool import POOL_NAME, SCHED_NAME

logger = logging.getLogger(__name__)


@dataclass
class FullLengthSendContext:
    media_ids: list[int]
    caption_html: str
    album_size: int


def is_full_length_send_time_scheduler(post: ScheduledTextPost) -> bool:
    return (post.name or "").strip() == SCHED_NAME


def _pool_randomize(post: ScheduledTextPost, pool) -> bool:
    if post.pool_randomize is not None:
        return bool(post.pool_randomize)
    return bool(pool and getattr(pool, "randomize_queue", False))


def pick_next_full_length_media(db: Session, *, pool_id: int, randomize: bool) -> Media | None:
    q = db.query(Media).filter(Media.pool_id == int(pool_id), Media.status == "approved")
    if randomize:
        rows = q.all()
        if not rows:
            return None
        import random

        return random.choice(rows)
    return q.order_by(Media.id.asc()).first()


def _peek_template_slot(post: ScheduledTextPost) -> tuple[int, str]:
    variations = post.get_content_variations()
    if variations:
        idx = (post.caption_rotation_index or 0) % len(variations)
        return idx, variations[idx]
    return 0, (post.content or "").strip()


def _advance_caption_rotation(post: ScheduledTextPost) -> None:
    variations = post.get_content_variations()
    n = len(variations)
    if n >= 2:
        idx = (post.caption_rotation_index or 0) % n
        post.caption_rotation_index = (idx + 1) % n


def build_full_length_send_context(db: Session, post: ScheduledTextPost) -> FullLengthSendContext | None:
    from app.models.content_pool import ContentPool

    if not post.pool_id:
        return None
    pool = db.query(ContentPool).filter(ContentPool.id == int(post.pool_id)).first()
    if not pool:
        return None

    media = pick_next_full_length_media(
        db,
        pool_id=int(pool.id),
        randomize=_pool_randomize(post, pool),
    )
    if media is None:
        return None

    _slot, template = _peek_template_slot(post)
    _advance_caption_rotation(post)
    body = build_movie_body_for_media(db, media)
    caption = inject_movie_body(template, body)
    return FullLengthSendContext(
        media_ids=[int(media.id)],
        caption_html=caption,
        album_size=1,
    )


def resolve_full_length_send_time_if_applicable(
    db: Session,
    post: ScheduledTextPost,
) -> FullLengthSendContext | None:
    if not is_full_length_send_time_scheduler(post):
        return None
    try:
        return build_full_length_send_context(db, post)
    except Exception:
        logger.exception("full_length send-time resolve failed post_id=%s", post.id)
        return None


def mark_full_length_media_posted(db: Session, media_ids: list[int]) -> None:
    """Chronological lane: dequeue by marking sent items posted."""
    if not media_ids:
        return
    for mid in media_ids:
        row = db.query(Media).filter(Media.id == int(mid)).first()
        if row and row.status == "approved":
            row.status = "posted"
    db.flush()
