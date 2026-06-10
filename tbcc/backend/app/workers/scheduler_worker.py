import os

from app.workers.celery_app import celery
from app.database.session import SessionLocal
from app.services.post_scheduler import check_and_schedule

_SCHEDULER_TICK_KEY = "tbcc:scheduler:tick_lock"


def _scheduler_tick_lock_ttl_s() -> int:
    raw = (os.getenv("TBCC_SCHEDULER_TICK_LOCK_S") or "90").strip()
    try:
        return max(30, min(600, int(raw)))
    except ValueError:
        return 90


def _try_acquire_scheduler_tick_lock() -> bool:
    try:
        import redis

        url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        r = redis.from_url(url, socket_connect_timeout=1.5)
        return bool(r.set(_SCHEDULER_TICK_KEY, "1", nx=True, ex=_scheduler_tick_lock_ttl_s()))
    except Exception:
        return True


def _release_scheduler_tick_lock() -> None:
    try:
        import redis

        url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        r = redis.from_url(url, socket_connect_timeout=1.5)
        r.delete(_SCHEDULER_TICK_KEY)
    except Exception:
        pass


def _scheduling_paused_by_focus() -> bool:
    try:
        from app.services.focus_profile import focus_flags

        return bool(focus_flags().get("pause_beat"))
    except Exception:
        return False


@celery.task(name="app.workers.scheduler_worker.run_schedule")
def run_schedule():
    if _scheduling_paused_by_focus():
        return {"skipped": "focus_pause_beat"}
    if not _try_acquire_scheduler_tick_lock():
        return {"skipped": "tick_lock_held"}
    db = SessionLocal()
    try:
        check_and_schedule(db)
        return {"ok": True}
    finally:
        db.close()
        _release_scheduler_tick_lock()
