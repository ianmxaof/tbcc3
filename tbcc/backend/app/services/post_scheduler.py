import logging
import os
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.database.session import SessionLocal
from app.models.channel import Channel
from app.models.content_pool import ContentPool
from app.models.scheduled_text_post import ScheduledTextPost
from app.workers.poster_worker import post_pool, post_scheduled_text

logger = logging.getLogger(__name__)

_POST_ENQUEUE_KEY = "tbcc:post:enqueued:{post_id}"
_POST_DUE_QUEUE_KEY = "tbcc:post:due_queue"
_POST_DRAIN_TICK_KEY = "tbcc:post:drain_tick"
SCHEDULER_POST_QUEUE = "post_scheduler"
POOL_POST_QUEUE = "post"


def pool_autopost_pause_when_overdue() -> bool:
    """Skip all pool auto-post while any scheduler row is past due."""
    return (os.getenv("TBCC_POOL_AUTOPOST_PAUSE_WHEN_OVERDUE") or "1").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def thumbnail_warm_pause_when_post_stalled() -> bool:
    return (os.getenv("TBCC_THUMBNAIL_WARM_PAUSE_WHEN_POST_STALLED") or "1").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _celery_queue_length(queue_name: str) -> int:
    try:
        import redis

        url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        r = redis.from_url(url, socket_connect_timeout=1.5)
        return int(r.llen(queue_name) or 0)
    except Exception:
        return 0


def scheduler_queue_length() -> int:
    return _celery_queue_length(SCHEDULER_POST_QUEUE)


def pool_queue_length() -> int:
    return _celery_queue_length(POOL_POST_QUEUE)


def posting_stalled_for_admission() -> bool:
    """True when scheduler lane is backed up or schedulers are overdue."""
    try:
        if int(schedulers_stall_summary().get("count") or 0) > 0:
            return True
    except Exception:
        pass
    threshold = post_queue_backlog_threshold()
    if scheduler_queue_length() >= threshold or pool_queue_length() >= threshold:
        return True
    return False


def post_batch_enqueue_enabled() -> bool:
    """Beat tick enqueues one drain task (single poster session lock) instead of N separate Celery jobs."""
    return (os.getenv("TBCC_POST_BATCH_ENQUEUE") or "1").strip().lower() in ("1", "true", "yes", "on")


def _post_drain_tick_ttl_s() -> int:
    raw = (os.getenv("TBCC_POST_DRAIN_TICK_S") or "600").strip()
    try:
        return max(60, min(3600, int(raw)))
    except ValueError:
        return 600


def _post_enqueue_dedupe_s() -> int:
    raw = (os.getenv("TBCC_POST_ENQUEUE_DEDUPE_S") or "180").strip()
    try:
        return max(30, min(3600, int(raw)))
    except ValueError:
        return 180


def _enqueue_dedupe_ttl_s(interval_minutes: int | None) -> int:
    """Hold enqueue lock through at least one full scheduler interval (prevents queue pile-up)."""
    base = _post_enqueue_dedupe_s()
    if interval_minutes is None:
        return base
    try:
        interval_s = max(60, int(interval_minutes) * 60)
    except (TypeError, ValueError):
        return base
    return max(base, min(interval_s, 86400))


def release_post_enqueue_lock(post_id: int) -> None:
    try:
        import redis

        url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        r = redis.from_url(url, socket_connect_timeout=1.5)
        r.delete(_POST_ENQUEUE_KEY.format(post_id=int(post_id)))
    except Exception:
        pass


def _enqueue_scheduled_post(post_id: int, *, interval_minutes: int | None = None) -> bool:
    """Skip duplicate Celery tasks for the same post while a send is pending or retrying."""
    ttl = _enqueue_dedupe_ttl_s(interval_minutes)
    try:
        import redis

        url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        r = redis.from_url(url, socket_connect_timeout=1.5)
        if not r.set(_POST_ENQUEUE_KEY.format(post_id=int(post_id)), "1", nx=True, ex=ttl):
            return False
    except Exception:
        pass
    if post_batch_enqueue_enabled():
        _enqueue_scheduled_post_batch(int(post_id))
        return True
    post_scheduled_text.delay(int(post_id))
    return True


def scheduled_drain_snapshot() -> dict[str, Any]:
    """Redis due-queue + scheduler-lane depth for watchdog and health."""
    out: dict[str, Any] = {
        "due_len": 0,
        "drain_tick": False,
        "scheduler_queue": 0,
        "enqueue_locks": 0,
    }
    try:
        import redis

        url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        r = redis.from_url(url, socket_connect_timeout=1.5)
        out["due_len"] = int(r.llen(_POST_DUE_QUEUE_KEY) or 0)
        out["drain_tick"] = bool(r.get(_POST_DRAIN_TICK_KEY))
        out["scheduler_queue"] = scheduler_queue_length()
        out["enqueue_locks"] = sum(
            1 for _ in r.scan_iter(match="tbcc:post:enqueued:*", count=200)
        )
    except Exception as e:
        out["error"] = str(e)[:200]
    return out


def ensure_scheduled_drain_running() -> dict[str, Any]:
    """
    Guarantee a drain_scheduled_post_queue consumer when Redis due_queue has work.

    Fixes stale drain_tick (tick set but no Celery task) and orphaned due_queue rows
    after a long drain or resume/purge race.
    """
    from app.workers.poster_worker import drain_scheduled_post_queue

    snap = scheduled_drain_snapshot()
    due_len = int(snap.get("due_len") or 0)
    sched_len = int(snap.get("scheduler_queue") or 0)
    tick_set = bool(snap.get("drain_tick"))
    if due_len <= 0:
        return {"ok": True, "action": "none", **snap}

    if tick_set and sched_len == 0:
        release_post_drain_tick_lock()
        tick_set = False

    try:
        import redis

        url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        r = redis.from_url(url, socket_connect_timeout=1.5)
        if not tick_set and r.set(_POST_DRAIN_TICK_KEY, "1", nx=True, ex=_post_drain_tick_ttl_s()):
            drain_scheduled_post_queue.delay()
            return {"ok": True, "action": "spawn_drain", **snap}
    except Exception as e:
        try:
            drain_scheduled_post_queue.delay()
            return {"ok": True, "action": "spawn_drain_fallback", "error": str(e)[:120], **snap}
        except Exception as e2:
            return {"ok": False, "action": "spawn_failed", "error": str(e2)[:200], **snap}

    return {"ok": True, "action": "drain_pending", **snap}


def _enqueue_scheduled_post_batch(post_id: int) -> None:
    """Append to Redis due queue; ensure a drain worker is scheduled."""
    try:
        import redis

        url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        r = redis.from_url(url, socket_connect_timeout=1.5)
        r.rpush(_POST_DUE_QUEUE_KEY, str(int(post_id)))
        ensure_scheduled_drain_running()
    except Exception:
        post_scheduled_text.delay(int(post_id))


def pop_scheduled_post_due_queue(*, max_items: int = 64) -> list[int]:
    """Drain post ids queued by check_and_schedule for one batched Celery send."""
    try:
        import redis

        url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        r = redis.from_url(url, socket_connect_timeout=1.5)
        out: list[int] = []
        for _ in range(max(1, min(200, int(max_items)))):
            raw = r.lpop(_POST_DUE_QUEUE_KEY)
            if not raw:
                break
            try:
                out.append(int(raw))
            except (TypeError, ValueError):
                continue
        return out
    except Exception:
        return []


def release_post_drain_tick_lock() -> None:
    try:
        import redis

        url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        r = redis.from_url(url, socket_connect_timeout=1.5)
        r.delete(_POST_DRAIN_TICK_KEY)
    except Exception:
        pass


def requeue_scheduled_post_due_ids(post_ids: list[int]) -> int:
    """Put post ids back on the Redis due queue after a drain abort (e.g. poster lock timeout)."""
    ids = [int(x) for x in post_ids if x is not None]
    if not ids:
        return 0
    try:
        import redis

        url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        r = redis.from_url(url, socket_connect_timeout=1.5)
        pipe = r.pipeline()
        for pid in ids:
            pipe.rpush(_POST_DUE_QUEUE_KEY, str(pid))
        pipe.execute()
        return len(ids)
    except Exception:
        return 0


def scheduler_drain_in_flight() -> bool:
    """True when due work exists and a drain consumer task is already on the scheduler queue."""
    snap = scheduled_drain_snapshot()
    due_len = int(snap.get("due_len") or 0)
    sched_len = int(snap.get("scheduler_queue") or 0)
    return due_len > 0 and sched_len > 0


def pool_auto_post_enabled() -> bool:
    """Pool interval cron via Beat → check_and_schedule. Set TBCC_POOL_AUTO_POST=0 to disable."""
    return (os.getenv("TBCC_POOL_AUTO_POST") or "1").strip().lower() in ("1", "true", "yes", "on")


def post_queue_backlog_threshold() -> int:
    """Health banner + auto-remediate when post queue depth reaches this (default 5)."""
    raw = (os.getenv("TBCC_POST_QUEUE_BACKLOG_THRESHOLD") or "5").strip()
    try:
        return max(1, min(50, int(raw)))
    except ValueError:
        return 5


def scheduler_stall_minutes() -> int:
    """Treat schedulers this many minutes past due as stalled for auto-resume."""
    raw = (os.getenv("TBCC_SCHEDULER_STALL_MINUTES") or "15").strip()
    try:
        return max(1, min(720, int(raw)))
    except ValueError:
        return 15


def _post_pool_max_queue_depth() -> int:
    """Skip pool auto-post when the post queue is this deep — scheduled posts take priority."""
    raw = (os.getenv("TBCC_POST_POOL_MAX_QUEUE_DEPTH") or "3").strip()
    try:
        return max(0, min(50, int(raw)))
    except ValueError:
        return 3


def _minutes_overdue(post: ScheduledTextPost, now: datetime) -> float | None:
    if post.interval_minutes is None or int(post.interval_minutes or 0) <= 0:
        return None
    if post.last_posted_at is None:
        return None
    return (now - post.last_posted_at).total_seconds() / 60 - float(post.interval_minutes)


def count_overdue_scheduled_posts(
    db: Session,
    *,
    min_overdue_minutes: float = 0.0,
) -> list[dict[str, Any]]:
    """Recurring schedulers past due by at least min_overdue_minutes."""
    now = datetime.utcnow()
    out: list[dict[str, Any]] = []
    rows = (
        db.query(ScheduledTextPost)
        .filter(
            ScheduledTextPost.interval_minutes.isnot(None),
            ScheduledTextPost.posting_auto_paused_at.is_(None),
        )
        .all()
    )
    for post in rows:
        overdue = _minutes_overdue(post, now)
        if overdue is None:
            continue
        if overdue >= min_overdue_minutes:
            out.append(
                {
                    "id": int(post.id),
                    "name": post.name,
                    "pool_id": post.pool_id,
                    "channel_id": post.channel_id,
                    "overdue_minutes": round(overdue, 1),
                }
            )
    out.sort(key=lambda x: -float(x["overdue_minutes"]))
    return out


def schedulers_stall_summary(*, min_overdue_minutes: float | None = None) -> dict[str, Any]:
    """Overdue scheduler snapshot for health checks and auto-remediate."""
    threshold = scheduler_stall_minutes() if min_overdue_minutes is None else float(min_overdue_minutes)
    db = SessionLocal()
    try:
        overdue = count_overdue_scheduled_posts(db, min_overdue_minutes=threshold)
        return {
            "threshold_minutes": threshold,
            "count": len(overdue),
            "max_overdue_minutes": max((float(x["overdue_minutes"]) for x in overdue), default=0.0),
            "posts": overdue[:12],
        }
    finally:
        db.close()


def _pool_ids_blocked_by_overdue_schedulers(db: Session, now: datetime) -> set[int]:
    """Pools tied to a due scheduler row — skip pool auto-post on that lane."""
    blocked: set[int] = set()
    for row in count_overdue_scheduled_posts(db, min_overdue_minutes=0.0):
        pid = row.get("pool_id")
        if pid is not None:
            blocked.add(int(pid))
    return blocked


def prioritize_scheduled_post_lane(db: Session) -> dict[str, Any]:
    """
    Strict scheduler priority: purge pool jobs from Celery post queue when any scheduler is due.
    Returns summary for logs/health remediate.
    """
    overdue_any = count_overdue_scheduled_posts(db, min_overdue_minutes=0.0)
    if not overdue_any:
        return {"ok": True, "action": "none", "overdue_count": 0}
    from app.services.celery_queue_ops import purge_post_pool_tasks_from_queue

    purged = purge_post_pool_tasks_from_queue()
    return {
        "ok": True,
        "action": "purge_post_pool",
        "overdue_count": len(overdue_any),
        "purge": purged,
    }


def _post_queue_length() -> int:
    """Scheduler lane depth (post_scheduler queue)."""
    return scheduler_queue_length()


def clear_post_scheduling_redis_state() -> dict[str, int]:
    """Release enqueue/drain locks so Beat can re-queue overdue scheduled posts."""
    cleared: dict[str, int] = {"enqueue_keys": 0, "due_queue": 0, "drain_tick": 0}
    try:
        import redis

        url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        r = redis.from_url(url, socket_connect_timeout=1.5)
        for key in r.scan_iter(match="tbcc:post:enqueued:*", count=200):
            cleared["enqueue_keys"] += int(r.delete(key) or 0)
        cleared["due_queue"] = int(r.delete(_POST_DUE_QUEUE_KEY) or 0)
        cleared["drain_tick"] = int(r.delete(_POST_DRAIN_TICK_KEY) or 0)
    except Exception:
        pass
    return cleared


def _migrate_scheduler_tasks_off_post_queue() -> dict[str, Any]:
    """Move legacy scheduler tasks off the pool post queue after post_scheduler split."""
    from app.services.celery_queue_ops import purge_queue_tasks_matching

    return purge_queue_tasks_matching(
        POOL_POST_QUEUE,
        task_substrings=[
            "drain_scheduled_post_queue",
            "post_scheduled_text",
        ],
    )


def nudge_scheduled_posting() -> dict[str, Any]:
    """
    Gentle scheduler recovery: re-run Beat scan and kick the drain worker.
    Does not purge Celery queues or clear enqueue locks — safe to run every watch tick.
    """
    snap = scheduled_drain_snapshot()
    if (
        int(snap.get("due_len") or 0) > 0
        and bool(snap.get("drain_tick"))
        and int(snap.get("scheduler_queue") or 0) == 0
    ):
        release_post_drain_tick_lock()

    out: dict[str, Any] = {"ok": True, "mode": "nudge"}
    db = SessionLocal()
    try:
        out["priority"] = prioritize_scheduled_post_lane(db)
        check_and_schedule(db)
        out["scheduled"] = True
    finally:
        db.close()
    out["drain"] = ensure_scheduled_drain_running()
    out["snap"] = scheduled_drain_snapshot()
    out["post_queue_length"] = _post_queue_length()
    return out


def resume_scheduled_posting(*, purge_post_queue: bool = True, force: bool = False) -> dict:
    """
    Hard unblock for stalled schedulers: optionally purge stale queue tasks, clear Redis
    enqueue locks, re-run check_and_schedule. Skips scheduler-queue purge when a drain is
    in flight unless force=True (avoids killing an active batch send).
    """
    from app.services.celery_queue_ops import purge_celery_queues, purge_post_pool_tasks_from_queue

    in_flight = scheduler_drain_in_flight()
    if purge_post_queue and in_flight and not force:
        purge_post_queue = False

    out: dict = {"ok": True, "mode": "hard", "purge_skipped_in_flight": in_flight and not force}
    out["migrate_post_queue"] = _migrate_scheduler_tasks_off_post_queue()
    if purge_post_queue:
        out["purge"] = purge_celery_queues([SCHEDULER_POST_QUEUE, POOL_POST_QUEUE], min_length=0)
    else:
        out["purge_pool_only"] = purge_post_pool_tasks_from_queue()
    out["redis"] = clear_post_scheduling_redis_state()
    db = SessionLocal()
    try:
        out["priority"] = prioritize_scheduled_post_lane(db)
        check_and_schedule(db)
        out["scheduled"] = True
    finally:
        db.close()
    out["drain"] = ensure_scheduled_drain_running()
    out["post_queue_length"] = _post_queue_length()
    return out


def _dedupe_campaign_leaders(posts: list[ScheduledTextPost]) -> list[ScheduledTextPost]:
    """Enqueue one Celery task per multi-channel campaign (lowest row id); keep every non-campaign post."""
    seen: set[str] = set()
    out: list[ScheduledTextPost] = []
    for p in sorted(posts, key=lambda x: x.id):
        cg = getattr(p, "campaign_group_id", None)
        if not cg:
            out.append(p)
            continue
        if cg in seen:
            continue
        seen.add(cg)
        out.append(p)
    return out


def _schedule_pool_interval_posts(
    db: Session,
    now: datetime,
    *,
    blocked_pool_ids: set[int] | None = None,
) -> None:
    if not pool_auto_post_enabled():
        return
    if pool_autopost_pause_when_overdue():
        overdue_n = len(count_overdue_scheduled_posts(db, min_overdue_minutes=0.0))
        if overdue_n > 0:
            logger.info(
                "Skipping all pool auto-post — %s scheduler(s) overdue (TBCC_POOL_AUTOPOST_PAUSE_WHEN_OVERDUE)",
                overdue_n,
            )
            return
    blocked = blocked_pool_ids or set()
    if blocked:
        logger.info(
            "Skipping pool auto-post for %s pool(s) with overdue schedulers: %s",
            len(blocked),
            sorted(blocked)[:8],
        )
    max_depth = _post_pool_max_queue_depth()
    depth = pool_queue_length()
    if max_depth >= 0 and depth > max_depth:
        logger.info(
            "Skipping pool auto-post — post queue depth %s > max %s (scheduled posts prioritized)",
            depth,
            max_depth,
        )
        return
    pools = db.query(ContentPool).all()
    for pool in pools:
        if int(pool.id) in blocked:
            continue
        if getattr(pool, "auto_post_enabled", True) is False:
            continue
        channel = (
            db.query(Channel).filter(Channel.id == pool.channel_id).first()
            if pool.channel_id
            else None
        )
        if not channel:
            continue
        interval = max(1, int(pool.interval_minutes or 60))
        if pool.last_posted is None:
            should_post = True
        else:
            minutes_since = (now - pool.last_posted).total_seconds() / 60
            should_post = minutes_since >= interval
        if should_post:
            post_pool.delay(pool.id, channel.identifier)
            pool.last_posted = now


def check_and_schedule(db: Session):
    now = datetime.utcnow()

    priority = prioritize_scheduled_post_lane(db)
    blocked_pools = _pool_ids_blocked_by_overdue_schedulers(db, now)

    # Scheduled posts first — pool auto-post must not flood the solo Celery-Post worker queue.
    one_time_due = (
        db.query(ScheduledTextPost)
        .filter(
            ScheduledTextPost.interval_minutes.is_(None),
            ScheduledTextPost.sent_at.is_(None),
            ScheduledTextPost.scheduled_at.isnot(None),
            ScheduledTextPost.scheduled_at <= now,
            ScheduledTextPost.posting_auto_paused_at.is_(None),
        )
        .all()
    )
    for post in _dedupe_campaign_leaders(one_time_due):
        _enqueue_scheduled_post(post.id, interval_minutes=None)

    recurring = (
        db.query(ScheduledTextPost)
        .filter(
            ScheduledTextPost.interval_minutes.isnot(None),
            ScheduledTextPost.posting_auto_paused_at.is_(None),
        )
        .all()
    )
    recurring_due = []
    for post in recurring:
        if post.last_posted_at is None:
            # First run: API clears scheduled_at for interval jobs, so nothing else selects these rows.
            recurring_due.append(post)
            continue
        if (now - post.last_posted_at).total_seconds() / 60 >= post.interval_minutes:
            recurring_due.append(post)
    for post in _dedupe_campaign_leaders(recurring_due):
        _enqueue_scheduled_post(post.id, interval_minutes=post.interval_minutes)

    _schedule_pool_interval_posts(db, now, blocked_pool_ids=blocked_pools)

    db.commit()
    ensure_scheduled_drain_running()
    if priority.get("overdue_count", 0) > 0:
        logger.debug(
            "check_and_schedule: %s overdue scheduler(s); priority=%s",
            priority["overdue_count"],
            priority.get("action"),
        )
