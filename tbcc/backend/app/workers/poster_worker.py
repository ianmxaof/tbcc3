import asyncio
import logging
import os
from datetime import datetime
from app.workers.celery_app import celery

logger = logging.getLogger(__name__)


@celery.task(name="app.workers.poster_worker.post_scheduled_text")
def post_scheduled_text(post_id: int):
    """Send a scheduled post (text, media, buttons) to its channel."""
    from telethon import TelegramClient
    from app.database.session import SessionLocal
    from app.models.scheduled_text_post import ScheduledTextPost
    from app.models.channel import Channel
    from app.services.scheduled_post_service import send_scheduled_post

    async def run():
        db = SessionLocal()
        try:
            post = db.query(ScheduledTextPost).filter(ScheduledTextPost.id == post_id).first()
            if not post:
                logger.warning("Scheduled text post %s not found", post_id)
                return
            channel = db.query(Channel).filter(Channel.id == post.channel_id).first()
            if not channel:
                logger.warning("Channel %s for scheduled post %s not found", post.channel_id, post_id)
                return
            is_recurring = post.interval_minutes is not None
            if not is_recurring and post.sent_at:
                logger.info("Scheduled text post %s already sent (one-time)", post_id)
                return
            client = TelegramClient(
                "admin",
                int(os.environ["API_ID"]),
                os.environ["API_HASH"],
            )
            await client.start()
            try:
                await send_scheduled_post(client, channel.identifier, post, db)
                now = datetime.utcnow()
                if is_recurring:
                    post.last_posted_at = now
                else:
                    post.sent_at = now
                db.commit()
                logger.info("Sent scheduled post %s to %s", post_id, channel.identifier)
            finally:
                await client.disconnect()
        except Exception as e:
            logger.exception("Post scheduled text failed: %s", e)
            raise
        finally:
            db.close()

    asyncio.run(run())


@celery.task(name="app.workers.poster_worker.post_pool")
def post_pool(pool_id: int, channel_identifier: str):
    from telethon import TelegramClient
    from app.services.album_service import post_pool_albums
    from app.database.session import SessionLocal
    from app.models.content_pool import ContentPool

    async def run():
        client = TelegramClient(
            "admin",
            int(os.environ["API_ID"]),
            os.environ["API_HASH"],
        )
        await client.start()
        db = SessionLocal()
        try:
            pool = db.query(ContentPool).filter(ContentPool.id == pool_id).first()
            album_size = pool.album_size if pool else 5
            randomize = bool(pool and getattr(pool, "randomize_queue", False))
            logger.info(
                "Posting pool %s to %s (album_size=%s randomize=%s)",
                pool_id,
                channel_identifier,
                album_size,
                randomize,
            )
            await post_pool_albums(
                client,
                channel_identifier,
                pool_id,
                db,
                album_size=album_size,
                randomize=randomize,
            )
        except Exception as e:
            logger.exception("Post pool failed: %s", e)
            raise
        finally:
            db.close()
            await client.disconnect()

    asyncio.run(run())
