"""Post imported media to Telegram channels, groups, or forum topics."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.channel import Channel
from app.models.media import Media
from app.services.album_service import post_media_ids_to_forum_topic
from app.services.telegram_admin import get_telegram_client, import_lock

logger = logging.getLogger(__name__)

router = APIRouter()


class ForumPostAlbumBody(BaseModel):
    channel_id: int = Field(..., description="TBCC channels.id (dashboard)")
    message_thread_id: int | None = Field(
        default=None,
        description="Forum topic id (message_thread_id). Omit or null to post to the channel/group main chat.",
    )
    media_ids: list[int] = Field(..., min_length=1)
    caption: str = ""
    mark_posted: bool = True


@router.post("/post-album")
async def forum_post_album(body: ForumPostAlbumBody, db: Session = Depends(get_db)):
    ch = db.query(Channel).filter(Channel.id == body.channel_id).first()
    if not ch:
        return {"ok": False, "error": "Channel not found"}
    # Ensure ids belong to this user’s DB (optional: restrict by pool’s channel later)
    rows = db.query(Media).filter(Media.id.in_(body.media_ids)).all()
    if len(rows) != len(body.media_ids):
        return {"ok": False, "error": "One or more media_ids do not exist"}

    async with import_lock():
        try:
            client = await get_telegram_client()
        except Exception as e:
            logger.warning("telegram client: %s", e)
            return {"ok": False, "error": str(e)}
        result = await post_media_ids_to_forum_topic(
            client,
            ch.identifier,
            body.message_thread_id,
            body.media_ids,
            db,
            caption=body.caption,
            mark_posted=body.mark_posted,
        )
    return result
