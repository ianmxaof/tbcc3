"""AOF FULL LENGTH pool + scheduler wiring (FIFO chronological feature films)."""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy.orm import Session

from app.services.aof_full_length_caption import full_length_caption_templates

logger = logging.getLogger(__name__)

POOL_NAME = "AOF FULL LENGTH POOL"
SCHED_NAME = "AOF FULL LENGTH SCHEDULER"
DISPLAY_NAME = "AOF FULL LENGTH"
CHANNEL_KEY = "full_length"


def configure_full_length_pool(pool) -> None:
    """Chronological rotation: FIFO queue, single-video posts."""
    pool.album_size = 1
    pool.randomize_queue = False
    pool.auto_post_enabled = True


def refresh_aof_full_length_scheduler(db: Session) -> dict[str, Any]:
    from app.models.content_pool import ContentPool
    from app.models.scheduled_text_post import ScheduledTextPost

    pool = db.query(ContentPool).filter(ContentPool.name == POOL_NAME).first()
    sched = (
        db.query(ScheduledTextPost)
        .filter(ScheduledTextPost.name == SCHED_NAME)
        .order_by(ScheduledTextPost.id.desc())
        .first()
    )
    if not pool:
        return {"ok": False, "error": "missing_pool"}
    if not sched:
        return {"ok": False, "error": "missing_scheduler", "pool_id": pool.id}

    templates = full_length_caption_templates()
    if not templates:
        return {"ok": False, "error": "no_caption_templates"}

    configure_full_length_pool(pool)
    sched.content = templates[0]
    sched.content_variations = json.dumps(templates)
    sched.album_variants_json = None
    sched.pool_id = pool.id
    sched.pool_only_mode = True
    sched.pool_randomize = False
    sched.album_size = 1
    sched.interval_minutes = max(int(sched.interval_minutes or 0), 360)
    db.commit()

    from app.models.media import Media

    approved = (
        db.query(Media)
        .filter(Media.pool_id == pool.id, Media.status == "approved")
        .count()
    )

    return {
        "ok": True,
        "scheduler_id": sched.id,
        "pool_id": pool.id,
        "caption_template_count": len(templates),
        "send_time_tag_caption": True,
        "fifo_chronological": True,
        "approved_queue_depth": approved,
    }
