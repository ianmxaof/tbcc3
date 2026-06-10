"""Post imported media to Telegram channels, groups, or forum topics."""

from __future__ import annotations



import logging



from fastapi import APIRouter, Depends

from pydantic import BaseModel, Field

from sqlalchemy.orm import Session



from app.database.session import get_db

from app.models.channel import Channel

from app.models.media import Media

from app.services.album_service import post_bot_messages_to_forum_topic, post_media_ids_to_forum_topic
from app.schemas.watermark_options import WatermarkOptions
from app.services.image_crop_pipeline import ImageCropSettings

from app.services.telegram_admin import (
    friendly_telegram_error,
    run_telegram_album_composer_io,
    get_telegram_client,
    import_lock,
)



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

    buttons: list[dict] = Field(

        default_factory=list,

        description='Inline URL buttons [{text, url}, ...] on the first album chunk.',

    )

    mark_posted: bool = True

    send_silent: bool = Field(

        default=False,

        description="Telethon silent=True — subscribers are not notified about the new post.",

    )





class ForumPostAlbumFromBotBody(BaseModel):

    channel_id: int = Field(..., description="TBCC channels.id (dashboard)")

    message_thread_id: int | None = None

    media_count: int = Field(..., ge=1, le=100)

    message_ids: list[int] = Field(default_factory=list, max_length=100)

    anchor_max_message_id: int | None = None

    bot_username: str = Field(..., min_length=1, max_length=128)

    caption: str = ""

    buttons: list[dict] = Field(default_factory=list)

    send_silent: bool = False

    append_send_promo: bool = False

    files: list[dict] = Field(default_factory=list, max_length=100)

    crop: ImageCropSettings | None = None

    watermark: WatermarkOptions | None = None





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

            send_silent=bool(body.send_silent),

            buttons=body.buttons or None,

        )

    return result





@router.post("/post-album-from-bot")

async def forum_post_album_from_bot(body: ForumPostAlbumFromBotBody, db: Session = Depends(get_db)):

    """Instant channel post for Album Composer — server-side copy from bot DM."""

    ch = db.query(Channel).filter(Channel.id == body.channel_id).first()

    if not ch:

        return {"ok": False, "error": "Channel not found"}

    from app.utils.telegram_peer import resolve_poster_peer
    from app.workers.poster_worker import _get_poster_client

    try:
        poster_client = await _get_poster_client()
        post_destination = await resolve_poster_peer(
            poster_client,
            ch.identifier,
            invite_fallback=getattr(ch, "invite_link", None),
        )
    except Exception as e:
        logger.warning("post-album-from-bot: resolve destination failed: %s", e)
        return {"ok": False, "error": friendly_telegram_error(e)}

    from app.api.import_ import (
        SavedFromBotFileItem,
        _album_composer_bot_token,
        _download_bot_api_file,
        _gallery_send_promo_item,
        _process_media_bytes,
        _watermark_should_apply,
    )
    from app.services.scheduled_post_service import _build_reply_markup

    promo_item = _gallery_send_promo_item(db) if body.append_send_promo else None
    bot_peer = body.bot_username.strip().lstrip("@")
    reply_markup = _build_reply_markup(body.buttons or [])
    crop = body.crop
    wm = body.watermark
    use_crop = crop is not None and crop.applies()
    use_wm = _watermark_should_apply(db, wm, context="album_composer")
    use_bytes = use_crop or use_wm

    if use_bytes:
        processed: list[tuple[bytes, str]] = []
        try:
            if body.files:
                token = _album_composer_bot_token()
                if not token:
                    return {"ok": False, "error": "TBCC_ALBUM_COMPOSER_BOT_TOKEN not set"}
                file_items = [SavedFromBotFileItem(**f) if isinstance(f, dict) else f for f in body.files]
                for fi in file_items:
                    data = await _download_bot_api_file(fi.file_id, token)
                    kind = (fi.kind or "photo").lower()
                    if kind not in ("photo", "video"):
                        kind = "photo"
                    data = _process_media_bytes(data, kind, db, crop=crop, wm=wm)
                    processed.append((data, kind))
            else:

                async def _download_telethon(storage):
                    nonlocal processed
                    items = await storage.download_bot_batch_bytes(
                        bot_peer,
                        body.media_count,
                        message_ids=body.message_ids or None,
                        anchor_max_message_id=body.anchor_max_message_id,
                    )
                    processed = [
                        (_process_media_bytes(data, kind, db, crop=crop, wm=wm), kind)
                        for data, kind in items
                    ]
                    return processed

                await run_telegram_album_composer_io(_download_telethon)
        except Exception as e:
            return {"ok": False, "error": f"Could not download from album bot: {e}"}

        if not processed:
            return {"ok": False, "error": "No media downloaded for watermark/crop send"}

        from app.services.telegram_storage import TelegramStorage

        try:
            poster_storage = TelegramStorage(poster_client)
            return await poster_storage.post_bytes_to_channel(
                post_destination,
                processed,
                body.message_thread_id,
                caption=body.caption,
                send_silent=bool(body.send_silent),
                reply_markup=reply_markup,
                promo_item=promo_item,
                skip_watermark=True,
            )
        except Exception as e:
            logger.warning("post-album-from-bot bytes pipeline failed: %s", e, exc_info=True)
            return {"ok": False, "error": friendly_telegram_error(e)}

    async def _job(storage):
        return await post_bot_messages_to_forum_topic(
            storage.client,
            bot_peer,
            post_destination,
            body.media_count,
            body.message_thread_id,
            caption=body.caption,
            send_silent=bool(body.send_silent),
            reply_markup=reply_markup,
            promo_item=promo_item,
            message_ids=body.message_ids or None,
            anchor_max_message_id=body.anchor_max_message_id,
            post_client=poster_client,
        )

    try:
        return await run_telegram_album_composer_io(_job)

    except Exception as e:

        logger.warning("post-album-from-bot failed: %s", e, exc_info=True)

        return {"ok": False, "error": friendly_telegram_error(e)}

