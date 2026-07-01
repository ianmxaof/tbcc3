import asyncio
import logging
import os
import random
import threading
from datetime import datetime
from pathlib import Path

from app.workers.celery_app import celery
from app.utils.telegram_peer import normalize_telethon_peer_identifier, resolve_poster_peer
from app.utils.telethon_session import (
    admin_session_stem,
    configure_telethon_sqlite_session,
    graceful_telethon_disconnect,
    poster_session_stem,
    prepare_session_sqlite_file,
    telethon_sessions_share_file,
)

logger = logging.getLogger(__name__)

_poster_client = None
# Each Celery task uses asyncio.run() → a new event loop. Never reuse _poster_client across tasks.
_poster_client_lock = threading.Lock()


def _begin_poster_async_task() -> None:
    """Drop any client tied to a previous task's closed event loop."""
    global _poster_client
    with _poster_client_lock:
        _poster_client = None


async def _poster_task_finally() -> None:
    await _reset_poster_client()


def _campaign_random_channel_enabled(leader) -> bool:
    return bool(getattr(leader, "campaign_random_channel", False))


def _pick_one_campaign_target(eligible: set[int]) -> set[int]:
    if not eligible:
        return set()
    return {random.choice(list(eligible))}


def _record_scheduled_send_metrics(
    db,
    *,
    post,
    channel,
    ok: bool,
    outcome=None,
    error_message: str | None = None,
):
    from app.services.content_performance import record_post_delivery_metric
    from app.services.post_analytics import record_post_outbound_event

    extra = None
    if outcome:
        extra = {}
        if getattr(outcome, "telegram_message_id", None):
            extra["telegram_message_id"] = outcome.telegram_message_id
            extra["caption_slot_index"] = outcome.caption_slot_index
        if getattr(outcome, "pack_modifier_id", None):
            extra["pack_modifier_id"] = outcome.pack_modifier_id
        if not extra:
            extra = None
    ev = record_post_outbound_event(
        db,
        event_type="scheduled_post_sent",
        channel_id=post.channel_id if post else None,
        scheduled_post_id=int(post.id) if post else None,
        ok=ok,
        error_message=error_message,
        extra=extra,
    )
    if ok and outcome and channel:
        record_post_delivery_metric(
            db,
            outbound_event=ev,
            event_type="scheduled_post_sent",
            channel=channel,
            outcome=outcome,
        )
        try:
            from app.services.feed_rhythm import record_delivery_shape

            had_media = bool(getattr(post, "pool_id", None)) or bool(
                getattr(post, "pool_collective_random", False)
            ) or bool(getattr(post, "media_ids", None))
            caption = getattr(post, "last_sent_caption_html", None) or getattr(post, "content", None)
            record_delivery_shape(
                db,
                channel_identifier=str(getattr(channel, "identifier", "")),
                scheduler_name=getattr(post, "name", None),
                had_media=had_media,
                caption_html=caption,
            )
        except Exception as e:
            logger.debug("feed rhythm hook: %s", e)
    return ev


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


def _try_bootstrap_poster_from_admin() -> bool:
    """
    Copy Telethon auth from admin.session into the poster session file (SQLite backup).
    Opt-in via TBCC_POSTER_AUTO_COPY_ADMIN_SESSION=1 so local dev does not require a manual copy.
    """
    flag = os.getenv("TBCC_POSTER_AUTO_COPY_ADMIN_SESSION", "").strip().lower()
    if flag not in {"1", "true", "yes", "on"}:
        return False
    admin_stem = admin_session_stem()
    poster_stem = poster_session_stem()
    if os.path.normcase(os.path.normpath(admin_stem)) == os.path.normcase(os.path.normpath(poster_stem)):
        return False
    admin_path = admin_stem + ".session"
    poster_path = poster_stem + ".session"
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
            "Bootstrapped poster Telethon session from %s -> %s (TBCC_POSTER_AUTO_COPY_ADMIN_SESSION)",
            admin_path,
            poster_path,
        )
        return True
    except Exception:
        logger.exception("Failed to bootstrap poster session from admin.session")
        return False


def _note_poster_session_stress(err: Exception, *, source: str = "poster") -> None:
    if "database is locked" not in str(err).lower():
        return
    try:
        from app.services.focus_profile import record_session_stress_event

        record_session_stress_event(source)
    except Exception:
        pass


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
        max_connect_attempts = max(1, int(os.getenv("TBCC_POSTER_CONNECT_ATTEMPTS", "5")))
        connect_delay = float(os.getenv("TBCC_POSTER_CONNECT_RETRY_S", "1.0"))
        last_err: Exception | None = None
        for attempt in range(max_connect_attempts):
            try:
                await client.connect()
                configure_telethon_sqlite_session(client)
                last_err = None
                break
            except Exception as e:
                last_err = e
                if "database is locked" not in str(e).lower() or attempt >= max_connect_attempts - 1:
                    raise
                _note_poster_session_stress(e, source="poster_connect")
                prepare_session_sqlite_file(poster_session_stem())
                await graceful_telethon_disconnect(client, pause_s=0)
                await asyncio.sleep(connect_delay * (attempt + 1))
        if last_err is not None:
            raise last_err
    if not await client.is_user_authorized():
        if _try_bootstrap_poster_from_admin():
            await client.disconnect()
            await client.connect()
        if await client.is_user_authorized():
            return
        stem = poster_session_stem()
        admin_stem = admin_session_stem()
        raise RuntimeError(
            f"Telegram poster session is not logged in ({stem}.session). Celery cannot prompt for a phone number. "
            f"Fix: ensure a logged-in admin session exists at {admin_stem}.session (same API_ID/API_HASH), then either "
            f"copy it to {stem}.session, set TBCC_POSTER_AUTO_COPY_ADMIN_SESSION=1 to copy on first use, or run a "
            f"one-time interactive Telethon login with session stem {Path(stem).name!r} under tbcc/backend."
        )


async def _get_poster_client():
    """One Telethon client per Celery task (same asyncio.run); never carry over to the next task."""
    from telethon import TelegramClient

    global _poster_client
    if not os.environ.get("API_ID") or not os.environ.get("API_HASH"):
        raise RuntimeError("Telegram API not configured (API_ID/API_HASH missing)")
    if telethon_sessions_share_file():
        logger.warning(
            "Poster and admin Telethon sessions share %s.session — set TBCC_POSTER_TELEGRAM_SESSION=admin_poster "
            "and TBCC_POSTER_AUTO_COPY_ADMIN_SESSION=1 in tbcc/.env",
            Path(poster_session_stem()).name,
        )
    with _poster_client_lock:
        if _poster_client is not None:
            return _poster_client
        stem = poster_session_stem()
        prepare_session_sqlite_file(stem)
        c = TelegramClient(
            stem,
            int(os.environ["API_ID"]),
            os.environ["API_HASH"],
        )
        try:
            await _ensure_poster_authorized(c)
        except Exception:
            await graceful_telethon_disconnect(c)
            raise
        _poster_client = c
        return _poster_client


async def _reset_poster_client() -> None:
    """Drop client for this task's event loop before asyncio.run() returns."""
    global _poster_client
    with _poster_client_lock:
        c = _poster_client
        _poster_client = None
    if c is not None:
        await graceful_telethon_disconnect(c)


async def _acquire_poster_session_lock() -> str:
    from app.services.telethon_session_lock import acquire_poster_session_lock_async

    return await acquire_poster_session_lock_async()


async def _release_poster_session_lock(token: str) -> None:
    if not token:
        return
    from app.services.telethon_session_lock import release_poster_session_lock_async

    await release_poster_session_lock_async(token)


@celery.task(name="app.workers.poster_worker.mirror_scheduled_post_to_buffer")
def mirror_scheduled_post_to_buffer(post_id: int):
    from app.services.scheduled_buffer_mirror import mirror_scheduled_post_to_buffer_sync

    mirror_scheduled_post_to_buffer_sync(int(post_id))


def _after_telegram_buffer_mirror(post_id: int, *, manual_trigger: bool) -> None:
    """Queue or run Buffer mirror immediately after a successful Telegram send."""
    if manual_trigger:
        from app.services.scheduled_buffer_mirror import mirror_scheduled_post_to_buffer_sync

        mirror_scheduled_post_to_buffer_sync(int(post_id))
        return
    try:
        mirror_scheduled_post_to_buffer.delay(int(post_id))
    except Exception:
        logger.debug("buffer mirror enqueue skipped", exc_info=True)


def _after_telegram_discord_mirror(post_id: int) -> None:
    """Optional Discord webhook after successful Telegram send."""
    from app.database.session import SessionLocal
    from app.models.scheduled_text_post import ScheduledTextPost
    from app.services.campaign_deploy_service import _run_discord

    db = SessionLocal()
    try:
        post = db.query(ScheduledTextPost).filter(ScheduledTextPost.id == int(post_id)).first()
        if not post or not bool(getattr(post, "discord_mirror_enabled", False)):
            return
        _run_discord(post, db)
    finally:
        db.close()


def _after_telegram_reddit_mirror(post_id: int) -> None:
    """Optional Reddit fan-out after successful Telegram send (dry-run until TBCC_REDDIT_EXECUTE=1)."""
    from app.database.session import SessionLocal
    from app.models.scheduled_text_post import ScheduledTextPost
    from app.services.reddit_fanout import run_reddit_mirror_for_scheduled_post

    db = SessionLocal()
    try:
        post = db.query(ScheduledTextPost).filter(ScheduledTextPost.id == int(post_id)).first()
        if not post:
            return
        run_reddit_mirror_for_scheduled_post(db, post)
    except Exception:
        logger.debug("reddit mirror skipped", exc_info=True)
    finally:
        db.close()


@celery.task(name="app.workers.poster_worker.mirror_scheduled_post_to_erome")
def mirror_scheduled_post_to_erome(post_id: int):
    from app.services.scheduled_erome_mirror import mirror_scheduled_post_to_erome_sync

    return mirror_scheduled_post_to_erome_sync(int(post_id))


def _after_telegram_erome_mirror(post_id: int) -> None:
    """Queue Erome album upload after successful Telegram send (Playwright on Celery worker)."""
    try:
        mirror_scheduled_post_to_erome.delay(int(post_id))
    except Exception:
        logger.debug("erome mirror enqueue skipped", exc_info=True)


async def _execute_post_scheduled_text(
    post_id: int,
    *,
    reshuffle_album: bool = False,
    manual_trigger: bool = False,
) -> None:
    """Send logic for one scheduled post (caller holds poster session lock when batching)."""
    from app.database.session import SessionLocal
    from app.models.channel import Channel
    from app.models.scheduled_text_post import ScheduledTextPost
    from app.services.scheduled_post_service import send_scheduled_campaign, send_scheduled_post

    db = SessionLocal()
    post_label = f"post_id={post_id}"
    try:
        post = db.query(ScheduledTextPost).filter(ScheduledTextPost.id == post_id).first()
        if not post:
            logger.warning("Scheduled text post %s not found", post_id)
            return
        post_label = (post.name or "").strip() or post_label
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
            if (
                not manual_trigger
                and is_recurring
                and not _is_recurring_due_now(post, datetime.utcnow())
            ):
                logger.info(
                    "Scheduled post %s skipped (not due yet; stale queue task)",
                    post_id,
                )
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
                    if manual_trigger:
                        due_targets = {
                            int(p.id)
                            for p in siblings
                            if not _is_scheduled_post_auto_paused(p) or reshuffle_album
                        }
                    else:
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
                    random_channel = _campaign_random_channel_enabled(leader)
                    if random_channel:
                        due_targets = _pick_one_campaign_target(due_targets)
                    from app.services.aof_vip_mirror import (
                        mirror_scheduled_post_to_vip,
                        should_mirror_scheduled_post,
                    )

                    leader_ch = db.query(Channel).filter(Channel.id == leader.channel_id).first()
                    if leader_ch and should_mirror_scheduled_post(db, leader, leader_ch):
                        await mirror_scheduled_post_to_vip(
                            client,
                            leader,
                            db,
                            reshuffle_album=reshuffle_album,
                        )
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
                        if random_channel and is_recurring:
                            p.last_posted_at = now
                        elif int(p.id) in sent_ids and is_recurring:
                            p.last_posted_at = now
                        elif int(p.id) in sent_ids:
                            p.sent_at = now
                    ch_map = {
                        c.id: c
                        for c in db.query(Channel).filter(
                            Channel.id.in_({p.channel_id for p in siblings})
                        ).all()
                    }
                    for p in siblings:
                        pid = int(p.id)
                        if random_channel and pid not in sent_ids and pid not in failed_ids:
                            continue
                        ch = ch_map.get(p.channel_id)
                        _record_scheduled_send_metrics(
                            db,
                            post=p,
                            channel=ch,
                            ok=pid in sent_ids,
                            outcome=campaign_result.outcomes.get(pid),
                            error_message=(
                                "campaign partial failure"
                                if pid in failed_ids
                                else None
                            ),
                        )
                    if not (random_channel and is_recurring):
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
                    from app.services.post_scheduler import release_post_enqueue_lock

                    release_post_enqueue_lock(int(leader.id))
                    logger.info(
                        "Campaign %s sent=%s failed=%s%s%s",
                        campaign_group_id,
                        len(sent_ids),
                        len(failed_ids),
                        " (reshuffle)" if reshuffle_album else "",
                        " (random channel)" if random_channel else "",
                    )
                    leader = siblings[0]
                    if sent_ids and getattr(leader, "buffer_mirror_enabled", False):
                        _after_telegram_buffer_mirror(
                            int(leader.id), manual_trigger=manual_trigger
                        )
                    if sent_ids and getattr(leader, "discord_mirror_enabled", False):
                        _after_telegram_discord_mirror(int(leader.id))
                    if sent_ids and getattr(leader, "reddit_mirror_enabled", False):
                        _after_telegram_reddit_mirror(int(leader.id))
                    if sent_ids and getattr(leader, "erome_mirror_enabled", False):
                        _after_telegram_erome_mirror(int(leader.id))
                    if sent_ids:
                        from app.services.caption_llm_rewrite import note_llm_send_completed

                        note_llm_send_completed(leader)
                    if failed_ids and campaign_result.first_error is not None:
                        logger.warning(
                            "Campaign %s had channel failures (first error): %s",
                            campaign_group_id,
                            campaign_result.first_error,
                        )
                else:
                    channel = db.query(Channel).filter(Channel.id == post.channel_id).first()
                    from app.services.aof_vip_mirror import (
                        mirror_scheduled_post_to_vip,
                        should_mirror_scheduled_post,
                    )

                    if channel and should_mirror_scheduled_post(db, post, channel):
                        await mirror_scheduled_post_to_vip(
                            client,
                            post,
                            db,
                            reshuffle_album=reshuffle_album,
                        )
                    outcome = await send_scheduled_post(
                        client,
                        channel.identifier,
                        post,
                        db,
                        reshuffle_album=reshuffle_album,
                        invite_fallback=getattr(channel, "invite_link", None),
                    )
                    now = datetime.utcnow()
                    if is_recurring:
                        post.last_posted_at = now
                    else:
                        post.sent_at = now
                    _clear_auto_pause_fields(post)
                    _record_scheduled_send_metrics(
                        db,
                        post=post,
                        channel=channel,
                        ok=True,
                        outcome=outcome,
                    )
                    db.commit()
                    from app.services.post_scheduler import release_post_enqueue_lock

                    release_post_enqueue_lock(int(post_id))
                    logger.info(
                        "Sent scheduled post %s to %s%s",
                        post_id,
                        channel.identifier,
                        " (reshuffle)" if reshuffle_album else "",
                    )
                    if getattr(post, "buffer_mirror_enabled", False):
                        _after_telegram_buffer_mirror(
                            int(post.id), manual_trigger=manual_trigger
                        )
                    if getattr(post, "discord_mirror_enabled", False):
                        _after_telegram_discord_mirror(int(post.id))
                    if getattr(post, "reddit_mirror_enabled", False):
                        _after_telegram_reddit_mirror(int(post.id))
                    if getattr(post, "erome_mirror_enabled", False):
                        _after_telegram_erome_mirror(int(post.id))
                    from app.services.caption_llm_rewrite import note_llm_send_completed

                    note_llm_send_completed(post)
                break
            except Exception as send_err:
                if attempt >= max_attempts or not _is_retryable_telegram_error(send_err):
                    raise
                logger.warning(
                    "post_scheduled_text retry %s/%s for %s due to: %s",
                    attempt,
                    max_attempts,
                    post_label,
                    send_err,
                )
                await _reset_poster_client()
                delay = min(30, 3 * attempt)
                if "database is locked" in str(send_err).lower():
                    _note_poster_session_stress(send_err, source="poster_send")
                    delay = max(delay, 8)
                await asyncio.sleep(delay)
    except Exception as e:
        logger.exception("Post scheduled text failed for %s: %s", post_label, e)
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
        try:
            from app.services.post_scheduler import release_post_enqueue_lock

            release_post_enqueue_lock(int(post_id))
        except Exception:
            logger.debug("enqueue lock release on failure skipped", exc_info=True)
        raise
    finally:
        db.close()


@celery.task(name="app.workers.poster_worker.post_scheduled_text")
def post_scheduled_text(post_id: int, reshuffle_album: bool = False, manual_trigger: bool = False):
    """Send a scheduled post (text, media, buttons) to its channel.

    reshuffle_album: when True, randomize promo + picked media order for this send only (does not
    change saved album_order_mode). Also allows one-time posts that already have sent_at to send again.
    manual_trigger: dashboard Post now — force send + run Buffer mirror in-process when enabled.
    """

    async def run():
        _begin_poster_async_task()
        lock_token = ""
        try:
            await _reset_poster_client()
            lock_token = await _acquire_poster_session_lock()
            await _execute_post_scheduled_text(
                post_id,
                reshuffle_album=reshuffle_album,
                manual_trigger=manual_trigger,
            )
        finally:
            await _reset_poster_client()
            await _release_poster_session_lock(lock_token)

    asyncio.run(run())


@celery.task(name="app.workers.poster_worker.drain_scheduled_post_queue")
def drain_scheduled_post_queue():
    """
    Process Beat-enqueued scheduled posts in one Celery job (one poster session lock).
    Manual dashboard triggers still use post_scheduled_text directly.
    """
    from app.services.post_scheduler import pop_scheduled_post_due_queue, release_post_drain_tick_lock

    ids = pop_scheduled_post_due_queue()
    if not ids:
        release_post_drain_tick_lock()
        return {"ok": True, "count": 0}

    seen: set[int] = set()
    ordered: list[int] = []
    for pid in ids:
        if pid in seen:
            continue
        seen.add(pid)
        ordered.append(pid)

    async def run():
        _begin_poster_async_task()
        lock_token = ""
        sent = 0
        failed = 0
        try:
            await _reset_poster_client()
            lock_token = await _acquire_poster_session_lock()
            for post_id in ordered:
                try:
                    await _execute_post_scheduled_text(int(post_id))
                    sent += 1
                except Exception:
                    failed += 1
                    logger.exception("drain_scheduled_post_queue: post_id=%s failed", post_id)
        finally:
            await _reset_poster_client()
            await _release_poster_session_lock(lock_token)
            release_post_drain_tick_lock()
        return {"ok": True, "count": len(ordered), "sent": sent, "failed": failed}

    return asyncio.run(run())


@celery.task(name="app.workers.poster_worker.post_listening_relay_message")
def post_listening_relay_message(
    channel_id: int,
    html_body: str,
    message_thread_id: int | None = None,
    send_silent: bool = True,
    copy_block_followup_html: str | None = None,
    copy_followups_json: str | None = None,
):
    """Post listening relay HTML; optional copy follow-up(s) under the link preview (text, media, buttons)."""
    from app.database.session import SessionLocal
    from app.models.channel import Channel
    from app.services.listening_relay_send import (
        RelayCopyFollowup,
        followups_from_json,
        send_relay_copy_followups,
    )

    body = (html_body or "").strip()
    if not body:
        logger.warning("post_listening_relay_message: empty body for channel_id=%s", channel_id)
        return

    followups = followups_from_json(copy_followups_json)
    if not followups and (copy_block_followup_html or "").strip():
        followups = [RelayCopyFollowup(html=(copy_block_followup_html or "").strip())]

    async def run():
        _begin_poster_async_task()
        lock_token = ""
        db = SessionLocal()
        try:
            await _reset_poster_client()
            lock_token = await _acquire_poster_session_lock()
            ch = db.query(Channel).filter(Channel.id == channel_id).first()
            if not ch:
                logger.warning("post_listening_relay_message: channel %s not found", channel_id)
                return
            max_attempts = max(1, int(os.getenv("TBCC_POSTER_MAX_ATTEMPTS", "3")))
            attempt = 0
            while True:
                attempt += 1
                try:
                    client = await _get_poster_client()
                    peer = await resolve_poster_peer(
                        client,
                        ch.identifier,
                        invite_fallback=getattr(ch, "invite_link", None),
                    )
                    from app.services.scheduled_post_service import _apply_telethon_html_to_kwargs

                    silent_kw = {"silent": True} if send_silent else {}
                    msg_kw: dict = {"reply_to": message_thread_id, **silent_kw}
                    _apply_telethon_html_to_kwargs(msg_kw, body[:4096], field="message")
                    sent = await client.send_message(peer, **msg_kw)
                    if followups:
                        reply_anchor = getattr(sent, "id", None) or message_thread_id
                        await send_relay_copy_followups(
                            client,
                            peer,
                            reply_anchor=reply_anchor,
                            followups=followups,
                            db=db,
                            send_silent=send_silent,
                        )
                    break
                except Exception as send_err:
                    if attempt >= max_attempts or not _is_retryable_telegram_error(send_err):
                        raise
                    logger.warning(
                        "post_listening_relay_message retry %s/%s channel_id=%s: %s",
                        attempt,
                        max_attempts,
                        channel_id,
                        send_err,
                    )
                    await _reset_poster_client()
                    await asyncio.sleep(min(10, 2 * attempt))
        finally:
            db.close()
            await _reset_poster_client()
            await _release_poster_session_lock(lock_token)

    asyncio.run(run())


@celery.task(name="app.workers.poster_worker.post_pool")
def post_pool(pool_id: int, channel_identifier: str, *, phase: str | None = None):
    from app.database.session import SessionLocal
    from app.models.content_pool import ContentPool
    from app.services.album_service import post_pool_albums
    from app.services.aof_vip_early_drop import (
        should_schedule_vip_early_drop,
        vip_channel_identifier,
        vip_early_drop_seconds,
    )
    from app.services.aof_vip_mirror import vip_album_size

    if phase is None:
        db0 = SessionLocal()
        try:
            pool0 = db0.query(ContentPool).filter(ContentPool.id == pool_id).first()
            if pool0 and should_schedule_vip_early_drop(pool0):
                delay = vip_early_drop_seconds()
                post_pool.apply_async(
                    args=(pool_id, channel_identifier),
                    kwargs={"phase": "vip"},
                    countdown=0,
                )
                post_pool.apply_async(
                    args=(pool_id, channel_identifier),
                    kwargs={"phase": "public"},
                    countdown=delay,
                )
                logger.info(
                    "vip early-drop scheduled pool=%s vip_now public_in=%ss",
                    pool_id,
                    delay,
                )
                return
        finally:
            db0.close()

    async def run():
        _begin_poster_async_task()
        lock_token = ""
        pool_label = f"pool_id={pool_id}"
        plan_db = SessionLocal()
        try:
            from app.models.channel import Channel

            pool = plan_db.query(ContentPool).filter(ContentPool.id == pool_id).first()
            if pool and (pool.name or "").strip():
                pool_label = (pool.name or "").strip()
            album_size = pool.album_size if pool else 5
            randomize = bool(pool and getattr(pool, "randomize_queue", False))
            ch = (
                plan_db.query(Channel).filter(Channel.id == pool.channel_id).first()
                if pool and pool.channel_id
                else None
            )
            invite_fb = getattr(ch, "invite_link", None) if ch else None
            target_peer = channel_identifier
            mark_posted = True
            if phase == "vip":
                vip_ident = vip_channel_identifier(plan_db)
                if not vip_ident:
                    logger.warning("vip early-drop: VIP channel not in DB — skip vip phase pool=%s", pool_id)
                    return
                target_peer = vip_ident
                mark_posted = False
                album_size = max(album_size, vip_album_size(pool_id=pool_id))
                logger.info("vip early-drop: posting pool %s to VIP %s album=%s", pool_id, vip_ident, album_size)
            elif phase == "public":
                logger.info("vip early-drop: posting pool %s to public %s", pool_id, channel_identifier)

            logger.info(
                "Posting pool %s to %s (album_size=%s randomize=%s phase=%s mark_posted=%s)",
                pool_id,
                target_peer,
                album_size,
                randomize,
                phase or "default",
                mark_posted,
            )
        finally:
            plan_db.close()

        try:
            await _reset_poster_client()
            lock_token = await _acquire_poster_session_lock()
            db = SessionLocal()
            try:
                max_attempts = max(1, int(os.getenv("TBCC_POSTER_MAX_ATTEMPTS", "3")))
                attempt = 0
                while True:
                    attempt += 1
                    try:
                        client = await _get_poster_client()
                        peer = await resolve_poster_peer(
                            client, target_peer, invite_fallback=invite_fb
                        )
                        await post_pool_albums(
                            client,
                            peer,
                            pool_id,
                            db,
                            album_size=album_size,
                            randomize=randomize,
                            mark_posted=mark_posted,
                        )
                        break
                    except Exception as send_err:
                        if attempt >= max_attempts or not _is_retryable_telegram_error(send_err):
                            raise
                        logger.warning(
                            "post_pool retry %s/%s for %s due to: %s",
                            attempt,
                            max_attempts,
                            pool_label,
                            send_err,
                        )
                        await _reset_poster_client()
                        delay = min(30, 3 * attempt)
                        if "database is locked" in str(send_err).lower():
                            _note_poster_session_stress(send_err, source="pool_send")
                            delay = max(delay, 8)
                        await asyncio.sleep(delay)

                from app.models.channel import Channel

                pool = db.query(ContentPool).filter(ContentPool.id == pool_id).first()
                ch = (
                    db.query(Channel).filter(Channel.id == pool.channel_id).first()
                    if pool and pool.channel_id
                    else None
                )
                if pool and (phase in (None, "public")):
                    pool.last_posted = datetime.utcnow()
                from app.services.post_analytics import record_post_outbound_event
                from app.services.content_performance import record_post_delivery_metric

                ev = record_post_outbound_event(
                    db,
                    event_type="pool_album_posted",
                    channel_id=pool.channel_id if pool else None,
                    pool_id=pool_id,
                    ok=True,
                )
                record_post_delivery_metric(
                    db,
                    outbound_event=ev,
                    event_type="pool_album_posted",
                    channel=ch,
                    pool_id=pool_id,
                    scheduler_name=(pool.name if pool else None),
                )
                db.commit()
                try:
                    from app.services.aof_feed_rhythm_v2 import maybe_queue_post_refill

                    maybe_queue_post_refill(db, pool_id=pool_id, phase=phase)
                except Exception:
                    logger.debug("post-refill hook skipped", exc_info=True)
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
                logger.exception("Post pool failed for %s: %s", pool_label, e)
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
            await _release_poster_session_lock(lock_token)

    asyncio.run(run())
