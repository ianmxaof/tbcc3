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
                from app.services.post_analytics import record_post_outbound_event

                record_post_outbound_event(
                    db,
                    event_type="scheduled_post_sent",
                    channel_id=post.channel_id,
                    scheduled_post_id=post_id,
                    ok=True,
                )
                db.commit()
                logger.info("Sent scheduled post %s to %s", post_id, channel.identifier)
            finally:
                await client.disconnect()
        except Exception as e:
            logger.exception("Post scheduled text failed: %s", e)
            try:
                from app.services.post_analytics import record_post_outbound_event

                db_fail = SessionLocal()
                try:
                    p2 = db_fail.query(ScheduledTextPost).filter(ScheduledTextPost.id == post_id).first()
                    ch_id = p2.channel_id if p2 else None
                    record_post_outbound_event(
                        db_fail,
                        event_type="scheduled_post_sent",
                        channel_id=ch_id,
                        scheduled_post_id=post_id,
                        ok=False,
                        error_message=str(e),
                    )
                    db_fail.commit()
                finally:
                    db_fail.close()
            except Exception:
                logger.debug("post analytics failure log skipped", exc_info=True)
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
            if pool:
                pool.last_posted = datetime.utcnow()
            from app.services.post_analytics import record_post_outbound_event

            record_post_outbound_event(
                db,
                event_type="pool_album_posted",
                channel_id=pool.channel_id if pool else None,
                pool_id=pool_id,
                ok=True,
            )
            db.commit()
            try:
                from app.models.channel import Channel as Ch
                from app.services.outbound_webhook import notify_outbound_webhook

                ch = db.query(Ch).filter(Ch.id == pool.channel_id).first() if pool else None
                if ch:
                    notify_outbound_webhook(
                        getattr(ch, "webhook_url", None),
                        {"event": "pool_album_posted", "pool_id": pool_id, "channel_id": ch.id},
                    )
            except Exception:
                logger.debug("pool webhook notify skipped", exc_info=True)
        except Exception as e:
            logger.exception("Post pool failed: %s", e)
            try:
                from app.services.post_analytics import record_post_outbound_event

                db_fail = SessionLocal()
                try:
                    pl = db_fail.query(ContentPool).filter(ContentPool.id == pool_id).first()
                    cid = pl.channel_id if pl else None
                    record_post_outbound_event(
                        db_fail,
                        event_type="pool_album_posted",
                        channel_id=cid,
                        pool_id=pool_id,
                        ok=False,
                        error_message=str(e),
                    )
                    db_fail.commit()
                finally:
                    db_fail.close()
            except Exception:
                logger.debug("post analytics failure log skipped", exc_info=True)
            raise
        finally:
            db.close()
            await client.disconnect()

    asyncio.run(run())
