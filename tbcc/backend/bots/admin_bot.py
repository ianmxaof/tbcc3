import logging
import os

from bots import __init__  # noqa: F401 - loads .env from tbcc/

from telethon import TelegramClient, events

from app.database.session import SessionLocal

from app.models.media import Media

from app.models.content_pool import ContentPool

from app.workers.poster_worker import post_pool

from app.models.channel import Channel

from app.data.aof_storage_hub_map import STORAGE_HUB_IDENT

from app.services.erome_telegram_ingest import (
    erome_auto_upload_enabled,
    erome_topic_setup_hint,
    format_erome_upload_reply,
    ingest_telegram_messages_to_erome,
    is_erome_storage_topic,
    is_storage_hub_chat,
)

from app.services.storage_topic_deposit import (

    default_deposit_media_types,

    format_deposit_error_text,

    format_deposit_success_text,

    forum_message_thread_id_from_telethon,

    parse_deposit_command,

    queue_storage_topic_deposit,

    resolve_deposit_limit,

)

from app.utils.telethon_session import (

    admin_bot_session_stem,

    bootstrap_admin_bot_session_from_admin,

    configure_telethon_sqlite_session,

    graceful_telethon_disconnect,

    prepare_session_sqlite_file,

)



_api_id = os.environ.get("API_ID", "").strip()

_api_hash = (os.environ.get("API_HASH") or "").strip()

if not _api_id or not _api_hash:

    raise SystemExit(

        "Missing API_ID or API_HASH. Set them in tbcc/.env (from my.telegram.org) and run from backend/."

    )



_session_stem = admin_bot_session_stem()

bootstrap_admin_bot_session_from_admin()

prepare_session_sqlite_file(_session_stem)

client = TelegramClient(_session_stem, int(_api_id), _api_hash)

ADMIN_ID = int(os.environ.get("ADMIN_TELEGRAM_ID", "0"))

logger = logging.getLogger(__name__)





@client.on(events.NewMessage(from_users=[ADMIN_ID], pattern=r"/status"))

async def cmd_status(event):

    db = SessionLocal()

    try:

        pending = db.query(Media).filter(Media.status == "pending").count()

        approved = db.query(Media).filter(Media.status == "approved").count()

        posted = db.query(Media).filter(Media.status == "posted").count()

        await event.reply(

            "📊 **TBCC Status**\n\n"

            f"⏳ Pending: {pending}\n"

            f"✅ Approved: {approved}\n"

            f"📤 Posted: {posted}"

        )

    finally:

        db.close()





@client.on(events.NewMessage(from_users=[ADMIN_ID], pattern=r"/approve (\d+)"))

async def cmd_approve(event):

    media_id = int(event.pattern_match.group(1))

    db = SessionLocal()

    try:

        media = db.get(Media, media_id)

        if media:

            media.status = "approved"

            db.commit()

            await event.reply(f"✅ Media {media_id} approved.")

        else:

            await event.reply(f"❌ Media {media_id} not found.")

    finally:

        db.close()





@client.on(events.NewMessage(from_users=[ADMIN_ID], pattern=r"/postnow (\d+)"))

async def cmd_postnow(event):

    pool_id = int(event.pattern_match.group(1))

    db = SessionLocal()

    try:

        pool = db.get(ContentPool, pool_id)

        if not pool:

            await event.reply(f"❌ Pool {pool_id} not found.")

            return

        channel = db.get(Channel, pool.channel_id) if pool.channel_id else None

        if not channel:

            await event.reply(f"❌ Pool {pool_id} has no channel.")

            return

        post_pool.delay(pool_id, channel.identifier)

        await event.reply(f"🚀 Posting pool {pool_id} now.")

    finally:

        db.close()





@client.on(events.NewMessage(from_users=[ADMIN_ID], pattern=r"/schedule"))

async def cmd_schedule(event):

    from app.services.post_scheduler import check_and_schedule

    db = SessionLocal()

    try:

        check_and_schedule(db)

        await event.reply("✅ Scheduler run complete.")

    finally:

        db.close()





def _is_storage_hub_chat(chat_id) -> bool:

    return is_storage_hub_chat(chat_id)


_erome_jobs: set[int] = set()


async def _run_erome_upload(event, *, title: str | None = None) -> None:
    thread_id = forum_message_thread_id_from_telethon(event.message)
    if not thread_id or not is_erome_storage_topic(thread_id):
        await event.reply(
            "❌ Erome uploads only work in the **Remote Upload Links** subtopic.\n"
            + erome_topic_setup_hint(),
            parse_mode="md",
        )
        return
    anchor = event.message
    if event.is_reply:
        try:
            anchor = await event.get_reply_message()
        except Exception:
            pass
    if not anchor or not getattr(anchor, "media", None):
        await event.reply(
            "Post media here or reply `/erome` to a photo/video (albums supported).",
            parse_mode="md",
        )
        return
    job_key = int(anchor.id)
    if job_key in _erome_jobs:
        return
    _erome_jobs.add(job_key)
    try:
        await event.reply("⏳ Downloading, watermarking, uploading to Erome…", parse_mode="md")
        report = await ingest_telegram_messages_to_erome(
            client,
            chat_id=int(event.chat_id),
            thread_id=int(thread_id),
            anchor_message=anchor,
            title=title,
        )
        await event.reply(format_erome_upload_reply(report, html=False), parse_mode="md")
    except Exception as e:
        logger.exception("erome telegram upload failed")
        await event.reply(f"❌ Erome upload error: {str(e)[:300]}", parse_mode="md")
    finally:
        _erome_jobs.discard(job_key)


@client.on(events.NewMessage(from_users=[ADMIN_ID], pattern=r"^/erome"))
async def cmd_erome(event):
    """
    In Remote Upload Links topic: reply to media (or attach media) → watermarked Erome album.
    Optional title: /erome My Album Title
    """
    if not _is_storage_hub_chat(event.chat_id):
        await event.reply("❌ `/erome` only works in Storage & Bot Hangar.", parse_mode="md")
        return
    raw = (getattr(event.message, "message", None) or "").strip()
    title = None
    if raw.lower().startswith("/erome"):
        rest = raw.split(None, 1)
        if len(rest) > 1:
            title = rest[1].strip()[:120] or None
    await _run_erome_upload(event, title=title)


@client.on(events.NewMessage(from_users=[ADMIN_ID]))
async def auto_erome_on_media(event):
    """Auto-upload when admin posts media in the Erome storage subtopic."""
    if not erome_auto_upload_enabled():
        return
    if not _is_storage_hub_chat(event.chat_id):
        return
    thread_id = forum_message_thread_id_from_telethon(event.message)
    if not is_erome_storage_topic(thread_id):
        return
    raw = (getattr(event.message, "message", None) or "").strip()
    if raw.startswith("/"):
        return
    if not getattr(event.message, "media", None):
        return
    await _run_erome_upload(event)


@client.on(events.NewMessage(from_users=[ADMIN_ID], pattern=r"^/deposit"))

async def cmd_deposit(event):

    """

    In Storage Hub forum topics: /deposit 15 → queue newest deduped videos into mapped pool.

    Optional: /deposit 15 both | photos | videos

    """

    parsed = parse_deposit_command(getattr(event.message, "message", None) or "")

    if parsed is None:

        await event.reply(

            "Usage: `/deposit 15` — import 15 new items into this topic's pool.\n"

            "Optional media filter: `videos` (default), `photos`, or `both`.\n"

            "Run inside a mapped Storage Hub subtopic (e.g. AOF MILF STORAGE).",

            parse_mode="md",

        )

        return



    if not _is_storage_hub_chat(event.chat_id):

        await event.reply(

            "❌ `/deposit` only works inside **Storage & Bot Hangar** forum topics.\n"

            f"Expected chat `{STORAGE_HUB_IDENT}`.",

            parse_mode="md",

        )

        return



    thread_id = forum_message_thread_id_from_telethon(event.message)

    if not thread_id:

        await event.reply(

            "❌ Post `/deposit` inside a forum **subtopic** (not General).\n"

            "Each AOF STORAGE topic maps to its receive-channel pool.",

        )

        return



    limit_raw, media_override = parsed

    limit = resolve_deposit_limit(limit_raw)

    media_types = media_override or default_deposit_media_types()



    db = SessionLocal()

    try:

        report = queue_storage_topic_deposit(

            db,

            message_thread_id=int(thread_id),

            limit=limit,

            media_types=media_types,

        )

    finally:

        db.close()



    if not report.get("ok"):

        await event.reply(format_deposit_error_text(report))

        return



    await event.reply(

        format_deposit_success_text(report, html=False),

        parse_mode="md",

    )





if __name__ == "__main__":

    import asyncio



    async def main():

        await client.start()

        configure_telethon_sqlite_session(client)

        print(f"TBCC admin bot online (session={_session_stem})")

        try:

            await client.run_until_disconnected()

        finally:

            await graceful_telethon_disconnect(client)



    asyncio.run(main())


