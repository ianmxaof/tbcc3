"""Celery: mirror Storage Hub topic media into matching main supergroup topic."""

from __future__ import annotations

import asyncio
import logging
import time

from app.workers.celery_app import celery

logger = logging.getLogger(__name__)

_MIRROR_LOCK_TIMEOUT_S = 300.0
_MIRROR_MAX_ATTEMPTS = 6
_DEPOSIT_MIRROR_LOCK_TIMEOUT_S = 120.0
_DEPOSIT_MIRROR_MAX_ATTEMPTS = 2


def _wait_import_job_terminal_sync(import_job_id: str, *, timeout_s: float = 3600) -> dict | None:
    from app.database.session import SessionLocal
    from app.models.import_job import ImportJob
    from app.services.import_pipeline import TERMINAL_STATUSES, job_to_public_dict

    if not import_job_id:
        return None
    deadline = time.monotonic() + max(60.0, timeout_s)
    while time.monotonic() < deadline:
        db = SessionLocal()
        try:
            job = db.query(ImportJob).filter(ImportJob.id == import_job_id).first()
            if job and job.status in TERMINAL_STATUSES:
                return job_to_public_dict(job)
        finally:
            db.close()
        time.sleep(2.0)
    return None


def _release_sessions_before_mirror() -> None:
    """Drop Telethon SQLite handles before mirror on the Celery worker loop."""
    from app.services.import_job_runner import _run_on_worker_loop
    from app.services.telegram_admin import reset_admin_client, reset_import_client

    async def _go() -> None:
        await reset_import_client()
        await reset_admin_client()
        await asyncio.sleep(3.0)

    _run_on_worker_loop(_go())


def _mirror_with_retries(
    storage_thread_id: int,
    main_thread_id: int,
    *,
    limit: int,
    media_types: str,
    prefer_import_session: bool,
    max_attempts: int = _MIRROR_MAX_ATTEMPTS,
    lock_timeout_s: float = _MIRROR_LOCK_TIMEOUT_S,
) -> dict:
    from app.services.aof_topic_mirror import mirror_storage_topic_to_main_sync

    last_err: Exception | None = None
    attempts = max(1, int(max_attempts))
    for attempt in range(attempts):
        if attempt:
            _release_sessions_before_mirror()
            time.sleep(min(48.0, 2.0 ** attempt))
        try:
            return mirror_storage_topic_to_main_sync(
                int(storage_thread_id),
                int(main_thread_id),
                limit=int(limit),
                media_types=media_types,
                prefer_import_session=prefer_import_session,
                use_worker_loop=True,
                lock_timeout_s=lock_timeout_s,
            )
        except Exception as e:
            last_err = e
            low = str(e).lower()
            if "database is locked" not in low and "sqlite" not in low:
                raise
            if attempt + 1 >= attempts:
                raise
            logger.warning(
                "topic mirror session locked (attempt %s/%s) %s→%s: %s",
                attempt + 1,
                attempts,
                storage_thread_id,
                main_thread_id,
                e,
            )
    if last_err is not None:
        raise last_err
    raise RuntimeError("mirror_with_retries failed without exception")


@celery.task(name="app.workers.topic_mirror_worker.mirror_topic_pair")
def mirror_topic_pair(
    storage_thread_id: int,
    main_thread_id: int,
    *,
    limit: int = 8,
    media_types: str = "both",
):
    from app.services.aof_topic_mirror import topic_mirror_enabled

    if not topic_mirror_enabled():
        return {"ok": True, "skipped": True}
    try:
        _release_sessions_before_mirror()
        stats = _mirror_with_retries(
            storage_thread_id,
            main_thread_id,
            limit=int(limit),
            media_types=media_types,
            prefer_import_session=False,
        )
        logger.info(
            "topic mirror %s→%s forwarded=%s uploaded=%s skipped_mirrored=%s",
            storage_thread_id,
            main_thread_id,
            stats.get("forwarded"),
            stats.get("uploaded"),
            stats.get("skipped_already_mirrored"),
        )
        return {"ok": True, **stats}
    except Exception as e:
        logger.exception("topic mirror failed: %s", e)
        return {"ok": False, "error": str(e)[:300]}


@celery.task(name="app.workers.topic_mirror_worker.mirror_after_deposit_job")
def mirror_after_deposit_job(
    import_job_id: str,
    storage_thread_id: int,
    main_thread_id: int,
    *,
    limit: int = 8,
    media_types: str = "both",
):
    """
    Deferred deposit mirror: wait for import job, release sessions, mirror with retries.
    Separate Celery task (not chained) so SQLite session files can unlock.
    """
    from app.services.aof_topic_mirror import topic_mirror_enabled

    if not topic_mirror_enabled():
        return {"ok": True, "skipped": True, "reason": "disabled"}

    job_body = _wait_import_job_terminal_sync(import_job_id)
    if not job_body:
        return {"ok": False, "error": "import_job_timeout", "job_id": import_job_id}

    if str(job_body.get("status") or "").lower() == "failed":
        return {
            "ok": True,
            "skipped": True,
            "reason": "import_failed",
            "job_id": import_job_id,
            "error": job_body.get("error"),
        }

    result = job_body.get("result") if isinstance(job_body.get("result"), dict) else {}
    stored = int(result.get("stored") or 0)
    if stored <= 0:
        return {"ok": True, "skipped": True, "reason": "nothing_stored", "stored": 0}

    try:
        _release_sessions_before_mirror()
        stats = _mirror_with_retries(
            storage_thread_id,
            main_thread_id,
            limit=int(limit),
            media_types=media_types,
            prefer_import_session=False,
            max_attempts=_DEPOSIT_MIRROR_MAX_ATTEMPTS,
            lock_timeout_s=_DEPOSIT_MIRROR_LOCK_TIMEOUT_S,
        )
        logger.info(
            "mirror_after_deposit_job %s %s→%s stored=%s forwarded=%s",
            import_job_id,
            storage_thread_id,
            main_thread_id,
            stored,
            stats.get("forwarded"),
        )
        return {"ok": True, "stored": stored, "import_job_id": import_job_id, **stats}
    except Exception as e:
        logger.exception("mirror_after_deposit_job failed job=%s: %s", import_job_id, e)
        return {"ok": False, "error": str(e)[:300], "import_job_id": import_job_id}


@celery.task(name="app.workers.topic_mirror_worker.mirror_after_channel_import")
def mirror_after_channel_import(
    import_out,
    storage_thread_id: int,
    main_thread_id: int,
    *,
    limit: int = 8,
    media_types: str = "both",
):
    """Legacy chain tail — delegates to deferred mirror logic when possible."""
    from app.services.aof_topic_mirror import topic_mirror_enabled

    if not topic_mirror_enabled():
        return {"ok": True, "skipped": True, "reason": "disabled"}

    stored = 0
    import_ok = False
    job_id = None
    if isinstance(import_out, dict):
        import_ok = bool(import_out.get("ok"))
        stored = int(import_out.get("stored") or 0)
        job_id = import_out.get("job_id")

    if not import_ok:
        return {"ok": True, "skipped": True, "reason": "import_failed"}
    if stored <= 0:
        return {"ok": True, "skipped": True, "reason": "nothing_stored", "stored": 0}

    if job_id:
        return mirror_after_deposit_job(
            str(job_id),
            int(storage_thread_id),
            int(main_thread_id),
            limit=int(limit),
            media_types=media_types,
        )

    try:
        _release_sessions_before_mirror()
        stats = _mirror_with_retries(
            storage_thread_id,
            main_thread_id,
            limit=int(limit),
            media_types=media_types,
            prefer_import_session=True,
        )
        return {"ok": True, "stored": stored, **stats}
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}
