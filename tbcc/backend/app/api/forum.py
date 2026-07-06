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


class ForumEromeUploadFromBotBody(BaseModel):
    """Album Composer → crop/watermark → Playwright Erome album upload."""

    media_count: int = Field(..., ge=1, le=100)
    message_ids: list[int] = Field(default_factory=list, max_length=100)
    anchor_max_message_id: int | None = None
    bot_username: str = Field(..., min_length=1, max_length=128)
    title: str | None = Field(None, max_length=120)
    description: str | None = Field(None, max_length=500)
    tags: list[str] = Field(default_factory=list, max_length=30)
    caption: str = ""
    files: list[dict] = Field(default_factory=list, max_length=100)
    crop: ImageCropSettings | None = None
    watermark: WatermarkOptions | None = None
    max_files: int | None = Field(None, ge=1, le=100)
    force_policy: bool = False


@router.post("/erome-upload-from-bot")
async def forum_erome_upload_from_bot(body: ForumEromeUploadFromBotBody, db: Session = Depends(get_db)):
    """Process staged album-bot media and publish one watermarked Erome album."""
    from app.api.import_ import (
        SavedFromBotFileItem,
        _download_album_bot_processed_bytes,
        _exc_detail,
    )
    from app.services.erome_telegram_ingest import (
        erome_max_files_per_album,
        format_erome_upload_reply,
        upload_processed_bytes_to_erome,
    )

    bot_peer = body.bot_username.strip().lstrip("@")
    crop = body.crop
    wm = body.watermark
    if wm is None:
        wm = WatermarkOptions(enabled=True)
    elif wm.enabled is None and not wm.skip:
        wm = wm.model_copy(update={"enabled": True})
    file_items = [SavedFromBotFileItem(**f) if isinstance(f, dict) else f for f in (body.files or [])]
    try:
        processed = await _download_album_bot_processed_bytes(
            bot_peer=bot_peer,
            media_count=body.media_count,
            message_ids=body.message_ids or None,
            anchor_max_message_id=body.anchor_max_message_id,
            files=file_items or None,
            db=db,
            crop=crop,
            wm=wm,
            context="erome",
        )
    except Exception as e:
        return {"ok": False, "error": f"Could not prepare media: {_exc_detail(e)}"}

    if not processed:
        return {"ok": False, "error": "No media downloaded for Erome upload"}

    from app.services.erome_upload_analytics import parse_erome_caption

    cap = (body.caption or "").strip()
    cap_title, cap_tags, cap_desc = parse_erome_caption(cap)
    title = (body.title or "").strip() or cap_title or (cap.split("\n", 1)[0].strip()[:120] if cap else None)
    tags = [t.strip() for t in (body.tags or []) if t.strip()] or cap_tags
    description = (body.description or "").strip() or cap_desc
    lim = body.max_files if body.max_files is not None else erome_max_files_per_album()
    if len(processed) > lim:
        processed = processed[:lim]

    wm_payload = wm.model_dump(exclude_none=True) if wm else None
    crop_payload = crop.model_dump(exclude_none=True) if crop else None

    report = await upload_processed_bytes_to_erome(
        processed,
        title=title,
        description=description,
        tags=tags,
        max_files=lim,
        skip_watermark=True,
        source="album_composer",
        watermark=wm_payload,
        crop=crop_payload,
        force_policy=body.force_policy,
        db=db,
    )
    if not report.get("ok"):
        return report
    # Producer signal for the idle governor: fresh erome album -> wake erome_view_sync.
    try:
        from app.services.idle_service_governor import touch_service_activity

        touch_service_activity("erome_view_sync")
    except Exception:
        pass
    report["reply_text"] = format_erome_upload_reply(report, html=False)
    return report


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
        _download_album_bot_processed_bytes,
        _exc_detail,
        _gallery_send_promo_item,
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
        file_items = [
            SavedFromBotFileItem(**f) if isinstance(f, dict) else f for f in (body.files or [])
        ]
        try:
            processed = await _download_album_bot_processed_bytes(
                bot_peer=bot_peer,
                media_count=body.media_count,
                message_ids=body.message_ids or None,
                anchor_max_message_id=body.anchor_max_message_id,
                files=file_items or None,
                db=db,
                crop=crop,
                wm=wm,
            )
        except Exception as e:
            return {"ok": False, "error": f"Could not download from album bot: {_exc_detail(e)}"}

        if not processed:
            return {"ok": False, "error": "No media downloaded for watermark/crop send"}

        from app.services.telegram_storage import TelegramStorage

        try:
            poster_storage = TelegramStorage(poster_client)
            result = await poster_storage.post_bytes_to_channel(
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
        if result.get("ok"):
            from app.services.main_channel_post_divider import maybe_send_main_channel_post_divider

            await maybe_send_main_channel_post_divider(
                poster_client,
                post_destination,
                db,
                channel_identifier=ch.identifier,
                message_thread_id=body.message_thread_id,
                send_silent=bool(body.send_silent),
            )
        return result

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
        result = await run_telegram_album_composer_io(_job)
    except Exception as e:

        logger.warning("post-album-from-bot failed: %s", e, exc_info=True)

        return {"ok": False, "error": friendly_telegram_error(e)}

    if result.get("ok"):
        from app.services.main_channel_post_divider import maybe_send_main_channel_post_divider

        await maybe_send_main_channel_post_divider(
            poster_client,
            post_destination,
            db,
            channel_identifier=ch.identifier,
            message_thread_id=body.message_thread_id,
            send_silent=bool(body.send_silent),
        )
    return result

