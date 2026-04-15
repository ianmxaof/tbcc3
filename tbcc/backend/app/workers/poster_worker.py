import asyncio
import logging
import os
from datetime import datetime

from app.workers.celery_app import celery

logger = logging.getLogger(__name__)

_poster_client = None
_poster_client_lock = asyncio.Lock()


def _poster_session_name() -> str:
    """Dedicated Telethon session file for poster worker to avoid cross-process SQLite locks."""
    name = (os.getenv("TBCC_POSTER_TELEGRAM_SESSION") or "admin_poster").strip()
    return name or "admin_poster"


def _is_retryable_telegram_error(err: Exception) -> bool:
    msg = str(err).lower()
    if "database is locked" in msg:
        return True
    if "connection to telegram failed" in msg or "timeouterror" in msg:
        return True
    return isinstance(err, (ConnectionError, TimeoutError, OSError))


async def _get_poster_client():
    """Lazy, long-lived Telethon client for this worker process."""
    from telethon import TelegramClient

    global _poster_client
    if not os.environ.get("API_ID") or not os.environ.get("API_HASH"):
        raise RuntimeError("Telegram API not configured (API_ID/API_HASH missing)")
    async with _poster_client_lock:
        if _poster_client is None:
            _poster_client = TelegramClient(
                _poster_session_name(),
                int(os.environ["API_ID"]),
                os.environ["API_HASH"],
            )
            await _poster_client.start()
        elif not _poster_client.is_connected():
            await _poster_client.connect()
        return _poster_client


async def _reset_poster_client() -> None:
    """Drop broken connection/session handle so the next attempt starts fresh."""
    global _poster_client
    async with _poster_client_lock:
        c = _poster_client
        _poster_client = None
        if c is not None:
            try:
                await c.disconnect()
            except Exception:
                logger.debug("poster client disconnect after error failed", exc_info=True)


@celery.task(name="app.workers.poster_worker.post_scheduled_text")
def post_scheduled_text(post_id: int, reshuffle_album: bool = False):
    """Send a scheduled post (text, media, buttons) to its channel.

    reshuffle_album: when True, randomize promo + picked media order for this send only (does not
    change saved album_order_mode). Also allows one-time posts that already have sent_at to send again.
    """
    from app.database.session import SessionLocal
    from app.models.channel import Channel
    from app.models.scheduled_text_post import ScheduledTextPost
    from app.services.scheduled_post_service import send_scheduled_campaign, send_scheduled_post

    async def run():
        db = SessionLocal()
        try:
            post = db.query(ScheduledTextPost).filter(ScheduledTextPost.id == post_id).first()
            if not post:
                logger.warning("Scheduled text post %s not found", post_id)
                return
            is_recurring = post.interval_minutes is not None
            if not is_recurring and post.sent_at and not reshuffle_album:
                logger.info("Scheduled text post %s already sent (one-time)", post_id)
                return

            campaign_group_id = getattr(post, "campaign_group_id", None)
            siblings: list = []
            if campaign_group_id:
                siblings = (
                    db.query(ScheduledTextPost)
                    .filter(ScheduledTextPost.campaign_group_id == campaign_group_id)
                    .order_by(ScheduledTextPost.id)
                    .all()
                )
                if not siblings:
                    return
                for p in siblings:
                    ch = db.query(Channel).filter(Channel.id == p.channel_id).first()
                    if not ch:
                        logger.warning("Channel %s for scheduled post %s not found", p.channel_id, p.id)
                        return
            else:
                channel = db.query(Channel).filter(Channel.id == post.channel_id).first()
                if not channel:
                    logger.warning("Channel %s for scheduled post %s not found", post.channel_id, post_id)
                    return

            max_attempts = max(1, int(os.getenv("TBCC_POSTER_MAX_ATTEMPTS", "3")))
            attempt = 0
            while True:
                attempt += 1
                try:
                    client = await _get_poster_client()
                    if campaign_group_id:
                        leader = siblings[0]
                        await send_scheduled_campaign(
                            client, leader, siblings, db, reshuffle_album=reshuffle_album
                        )
                        now = datetime.utcnow()
                        for p in siblings:
                            p.caption_rotation_index = leader.caption_rotation_index
                            p.album_carousel_index = leader.album_carousel_index
                            if is_recurring:
                                p.last_posted_at = now
                            else:
                                p.sent_at = now
                        from app.services.post_analytics import record_post_outbound_event

                        for p in siblings:
                            record_post_outbound_event(
                                db,
                                event_type="scheduled_post_sent",
                                channel_id=p.channel_id,
                                scheduled_post_id=p.id,
                                ok=True,
                            )
                        db.commit()
                        logger.info(
                            "Sent campaign %s (%s channels)%s",
                            campaign_group_id,
                            len(siblings),
                            " (reshuffle)" if reshuffle_album else "",
                        )
                    else:
                        channel = db.query(Channel).filter(Channel.id == post.channel_id).first()
                        await send_scheduled_post(
                            client, channel.identifier, post, db, reshuffle_album=reshuffle_album
                        )
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
                        logger.info(
                            "Sent scheduled post %s to %s%s",
                            post_id,
                            channel.identifier,
                            " (reshuffle)" if reshuffle_album else "",
                        )
                    break
                except Exception as send_err:
                    if attempt >= max_attempts or not _is_retryable_telegram_error(send_err):
                        raise
                    logger.warning(
                        "post_scheduled_text retry %s/%s for post_id=%s due to: %s",
                        attempt,
                        max_attempts,
                        post_id,
                        send_err,
                    )
                    await _reset_poster_client()
                    await asyncio.sleep(min(10, 2 * attempt))
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
    from app.database.session import SessionLocal
    from app.models.content_pool import ContentPool
    from app.services.album_service import post_pool_albums

    async def run():
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
            max_attempts = max(1, int(os.getenv("TBCC_POSTER_MAX_ATTEMPTS", "3")))
            attempt = 0
            while True:
                attempt += 1
                try:
                    client = await _get_poster_client()
                    await post_pool_albums(
                        client,
                        channel_identifier,
                        pool_id,
                        db,
                        album_size=album_size,
                        randomize=randomize,
                    )
                    break
                except Exception as send_err:
                    if attempt >= max_attempts or not _is_retryable_telegram_error(send_err):
                        raise
                    logger.warning(
                        "post_pool retry %s/%s for pool_id=%s due to: %s",
                        attempt,
                        max_attempts,
                        pool_id,
                        send_err,
                    )
                    await _reset_poster_client()
                    await asyncio.sleep(min(10, 2 * attempt))

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

    asyncio.run(run())
