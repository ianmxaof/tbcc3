import os
from bots import __init__  # noqa: F401 - loads .env from tbcc/
from telethon import TelegramClient, events
from app.database.session import SessionLocal
from app.models.media import Media
from app.models.content_pool import ContentPool
from app.workers.poster_worker import post_pool
from app.models.channel import Channel

_api_id = os.environ.get("API_ID", "").strip()
_api_hash = (os.environ.get("API_HASH") or "").strip()
if not _api_id or not _api_hash:
    raise SystemExit(
        "Missing API_ID or API_HASH. Set them in tbcc/.env (from my.telegram.org) and run from backend/."
    )

client = TelegramClient("admin", int(_api_id), _api_hash)
ADMIN_ID = int(os.environ.get("ADMIN_TELEGRAM_ID", "0"))


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


if __name__ == "__main__":
    import asyncio

    async def main():
        await client.start()
        await client.run_until_disconnected()

    asyncio.run(main())
