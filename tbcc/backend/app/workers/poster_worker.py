import asyncio
import logging
import os
import threading
from datetime import datetime

from app.workers.celery_app import celery

logger = logging.getLogger(__name__)

_poster_client = None
# Thread lock: each Celery task uses asyncio.run() → a new event loop. A module-level asyncio.Lock()
# would bind to the first loop and break later tasks; Telethon also forbids reusing a connected
# client across different loops.
_poster_client_lock = threading.Lock()


def _is_recurring_due_now(post, now_utc: datetime) -> bool:
    """Mirror scheduler logic so campaign retries only target currently due siblings."""
    interval = getattr(post, "interval_minutes", None)
    if interval is None:
        return False
    last_posted = getattr(post, "last_posted_at", None)
    if last_posted is None:
        return True
    return (now_utc - last_posted).total_seconds() / 60 >= float(interval)


def _auto_pause_streak_max() -> int:
    raw = (os.getenv("TBCC_SCHED_POST_AUTO_PAUSE_STREAK") or "5").strip()
    try:
        return max(0, int(raw))
    except ValueError:
        return 5


def _is_scheduled_post_auto_paused(p) -> bool:
    return getattr(p, "posting_auto_paused_at", None) is not None


def _clear_auto_pause_fields(p) -> None:
    p.send_failure_streak = 0
    p.posting_auto_paused_at = None
    p.posting_auto_pause_reason = None


def _note_send_failures_on_rows(posts: list, err: Exception | None) -> None:
    """Increment streak and optionally auto-pause rows (in-memory; caller commits)."""
    cap = _auto_pause_streak_max()
    if cap <= 0 or not posts:
        return
    msg = (str(err) if err else "send failed")[:512]
    now = datetime.utcnow()
    for p in posts:
        p.send_failure_streak = int(getattr(p, "send_failure_streak", None) or 0) + 1
        if int(p.send_failure_streak) >= cap:
            p.posting_auto_paused_at = now
            p.posting_auto_pause_reason = msg


def _poster_session_name() -> str:
    """Dedicated Telethon session file for poster worker to avoid cross-process SQLite locks."""
    name = (os.getenv("TBCC_POSTER_TELEGRAM_SESSION") or "admin_poster").strip()
    return name or "admin_poster"


def _try_bootstrap_poster_from_admin(session_basename: str) -> bool:
    """
    Copy Telethon auth from admin.session into the poster session file (SQLite backup).
    Opt-in via TBCC_POSTER_AUTO_COPY_ADMIN_SESSION=1 so local dev does not require a manual copy.
    """
    flag = os.getenv("TBCC_POSTER_AUTO_COPY_ADMIN_SESSION", "").strip().lower()
    if flag not in {"1", "true", "yes", "on"}:
        return False
    if session_basename == "admin":
        return False
    admin_path = os.path.abspath("admin.session")
    poster_path = os.path.abspath(f"{session_basename}.session")
    if not os.path.isfile(admin_path):
        logger.warning(
            "TBCC_POSTER_AUTO_COPY_ADMIN_SESSION is set but admin.session not found (%s)",
            admin_path,
        )
        return False
    try:
        import sqlite3

        src = sqlite3.connect(admin_path)
        dst = sqlite3.connect(poster_path)
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()
        logger.info(
            "Bootstrapped poster Telethon session from admin.session -> %s (TBCC_POSTER_AUTO_COPY_ADMIN_SESSION)",
            poster_path,
        )
        return True
    except Exception:
        logger.exception("Failed to bootstrap poster session from admin.session")
        return False


def _is_retryable_telegram_error(err: Exception) -> bool:
    msg = str(err).lower()
    if "database is locked" in msg:
        return True
    if "connection to telegram failed" in msg or "timeouterror" in msg:
        return True
    if "event loop must not change" in msg:
        return True
    return isinstance(err, (ConnectionError, TimeoutError, OSError))


async def _ensure_poster_authorized(client) -> None:
    """
    Connect without Telethon interactive login (never call start() in Celery — it prompts for phone on stdin).
    """
    if not client.is_connected():
        await client.connect()
    if not await client.is_user_authorized():
        session_name = _poster_session_name()
        if _try_bootstrap_poster_from_admin(session_name):
            await client.disconnect()
            await client.connect()
        if await client.is_user_authorized():
            return
        raise RuntimeError(
            f"Telegram poster session is not logged in ({session_name}.session — usually next to cwd, "
            f"often tbcc/backend). Celery cannot prompt for a phone number. "
            f"Fix: copy a logged-in admin.session to {session_name}.session (same API_ID/API_HASH), or run a "
            f"one-time interactive login from tbcc/backend with Telethon using session name '{session_name}'. "
            f"Override basename with TBCC_POSTER_TELEGRAM_SESSION, or set TBCC_POSTER_AUTO_COPY_ADMIN_SESSION=1 "
            f"to copy admin.session into the poster file on first use (dev convenience)."
        )


async def _get_poster_client():
    """Telethon client reused within one Celery task (one asyncio.run); see task finally block."""
    from telethon import TelegramClient

    global _poster_client
    if not os.environ.get("API_ID") or not os.environ.get("API_HASH"):
        raise RuntimeError("Telegram API not configured (API_ID/API_HASH missing)")
    with _poster_client_lock:
        need_new = _poster_client is None
    if need_new:
        c = TelegramClient(
            _poster_session_name(),
            int(os.environ["API_ID"]),
            os.environ["API_HASH"],
        )
        try:
            await _ensure_poster_authorized(c)
        except Exception:
            try:
                await c.disconnect()
            except Exception:
                logger.debug("poster client disconnect after auth failure", exc_info=True)
            raise
        with _poster_client_lock:
            if _poster_client is None:
                _poster_client = c
            else:
                await c.disconnect()
    else:
        with _poster_client_lock:
            client = _poster_client
        if client is not None and not client.is_connected():
            await _ensure_poster_authorized(client)
    with _poster_client_lock:
        return _poster_client


async def _reset_poster_client() -> None:
    """Drop broken connection/session handle so the next attempt starts fresh."""
    global _poster_client
    with _poster_client_lock:
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
        try:
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
                    if _is_scheduled_post_auto_paused(post) and not reshuffle_album:
                        logger.info("Scheduled post %s skipped (auto-paused)", post_id)
                        return

                max_attempts = max(1, int(os.getenv("TBCC_POSTER_MAX_ATTEMPTS", "3")))
                attempt = 0
                while True:
                    attempt += 1
                    try:
                        client = await _get_poster_client()
                        if campaign_group_id:
                            leader = siblings[0]
                            now = datetime.utcnow()
                            # Campaign jobs can partially succeed; only (re)send siblings currently due.
                            due_targets = {
                                int(p.id)
                                for p in siblings
                                if (not _is_scheduled_post_auto_paused(p) or reshuffle_album)
                                and (
                                    _is_recurring_due_now(p, now)
                                    or (not p.interval_minutes and not p.sent_at)
                                )
                            }
                            if not due_targets:
                                logger.info(
                                    "Campaign %s: nothing due to send (interval or auto-pause); skipping",
                                    campaign_group_id,
                                )
                                return
                            campaign_result = await send_scheduled_campaign(
                                client,
                                leader,
                                siblings,
                                db,
                                target_post_ids=due_targets or None,
                                reshuffle_album=reshuffle_album,
                            )
                            now = datetime.utcnow()
                            sent_ids = set(campaign_result.sent_post_ids)
                            failed_ids = set(campaign_result.failed_post_ids)
                            for p in siblings:
                                p.caption_rotation_index = leader.caption_rotation_index
                                p.album_carousel_index = leader.album_carousel_index
                                if int(p.id) in sent_ids and is_recurring:
                                    p.last_posted_at = now
                                elif int(p.id) in sent_ids:
                                    p.sent_at = now
                            from app.services.post_analytics import record_post_outbound_event

                            for p in siblings:
                                record_post_outbound_event(
                                    db,
                                    event_type="scheduled_post_sent",
                                    channel_id=p.channel_id,
                                    scheduled_post_id=p.id,
                                    ok=int(p.id) in sent_ids,
                                    error_message=(
                                        "campaign partial failure"
                                        if int(p.id) in failed_ids
                                        else None
                                    ),
                                )
                            # Throttle recurring failures: otherwise first-run failures are retried every beat tick.
                            for p in siblings:
                                if int(p.id) in failed_ids and p.interval_minutes:
                                    p.last_posted_at = now
                            for p in siblings:
                                if int(p.id) in sent_ids:
                                    _clear_auto_pause_fields(p)
                            _note_send_failures_on_rows(
                                [p for p in siblings if int(p.id) in failed_ids],
                                campaign_result.first_error,
                            )
                            db.commit()
                            logger.info(
                                "Campaign %s sent=%s failed=%s%s",
                                campaign_group_id,
                                len(sent_ids),
                                len(failed_ids),
                                " (reshuffle)" if reshuffle_album else "",
                            )
                            if failed_ids and campaign_result.first_error is not None:
                                logger.warning(
                                    "Campaign %s had channel failures (first error): %s",
                                    campaign_group_id,
                                    campaign_result.first_error,
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
                            _clear_auto_pause_fields(post)
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
                # Prevent runaway scheduler loops for recurring jobs when Telegram errors are permanent (e.g. bad username).
                try:
                    db_throttle = SessionLocal()
                    try:
                        p3 = db_throttle.query(ScheduledTextPost).filter(ScheduledTextPost.id == post_id).first()
                        if p3:
                            if p3.interval_minutes:
                                p3.last_posted_at = datetime.utcnow()
                            if _auto_pause_streak_max() > 0:
                                _note_send_failures_on_rows([p3], e)
                            db_throttle.commit()
                    finally:
                        db_throttle.close()
                except Exception:
                    logger.debug("recurring failure throttle / streak update skipped", exc_info=True)
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
        finally:
            await _reset_poster_client()

    asyncio.run(run())


@celery.task(name="app.workers.poster_worker.post_pool")
def post_pool(pool_id: int, channel_identifier: str):
    from app.database.session import SessionLocal
    from app.models.content_pool import ContentPool
    from app.services.album_service import post_pool_albums

    async def run():
        try:
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
        finally:
            await _reset_poster_client()

    asyncio.run(run())
