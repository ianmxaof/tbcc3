"""Execute a staged ImportJob: Telegram upload + DB index + optional enrich enqueue."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from telethon.errors.rpcerrorlist import ImageProcessFailedError

from app.database.session import SessionLocal
from app.models.import_job import ImportJob
from app.models.media import Media
from app.services.import_pipeline import (
    cleanup_staging_files,
    import_telegram_timeout_s,
    update_job,
)
from app.services.media_frame_sample import extract_video_frame_jpeg
from app.services.media_sniff import maybe_remux_mp4_for_playback
from app.services.telegram_admin import (
    friendly_telegram_error,
    reset_admin_client,
    reset_import_client,
    run_telegram_import_io,
)
from app.services.media_watermark import skip_watermark_context

logger = logging.getLogger(__name__)

# One event loop per Celery worker process — do not create/close a loop per import job
# (that leaves Telethon send/recv tasks pending and spams "Task was destroyed but it is pending").
_worker_loop: asyncio.AbstractEventLoop | None = None


def _worker_event_loop() -> asyncio.AbstractEventLoop:
    global _worker_loop
    if _worker_loop is None or _worker_loop.is_closed():
        _worker_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_worker_loop)
    return _worker_loop


def _run_on_worker_loop(coro):
    return _worker_event_loop().run_until_complete(coro)


def run_coroutine_on_worker_loop_safe(coro):
    """
    Run async IO on the Celery worker loop. If the loop is already running (Windows solo pool),
    execute in a one-shot thread with a fresh loop to avoid 'event loop is already running'.
    """
    loop = _worker_event_loop()
    if not loop.is_running():
        return loop.run_until_complete(coro)
    import concurrent.futures

    timeout = float(import_telegram_timeout_s()) + 60.0

    def _fresh_loop_run():
        new_loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(new_loop)
            return new_loop.run_until_complete(coro)
        finally:
            try:
                new_loop.close()
            except Exception:
                pass
            asyncio.set_event_loop(loop)

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(_fresh_loop_run).result(timeout=timeout)


def shutdown_import_worker_async() -> None:
    """Celery worker shutdown: disconnect Telethon and close the worker loop."""
    global _worker_loop
    loop = _worker_loop
    if loop is None or loop.is_closed():
        _worker_loop = None
        return
    try:
        if not loop.is_running():
            loop.run_until_complete(reset_admin_client())
            loop.run_until_complete(reset_import_client())
    except Exception:
        logger.debug("import worker telethon reset on shutdown", exc_info=True)
    try:
        loop.close()
    except Exception:
        pass
    _worker_loop = None
    try:
        asyncio.set_event_loop(None)
    except Exception:
        pass


def _prepare_bytes(job: ImportJob, raw: bytes) -> tuple[bytes, str]:
    data = maybe_remux_mp4_for_playback(raw)
    mt = (job.media_type or "photo").lower()
    if mt not in ("photo", "video", "document"):
        mt = "photo"
    return data, mt


def _maybe_write_poster(job: ImportJob, data: bytes, mt: str) -> str | None:
    if mt != "video":
        return None
    frame = extract_video_frame_jpeg(data)
    if not frame:
        return None
    poster = Path(job.staging_path or "").parent / f"{job.id}_poster.jpg"
    poster.write_bytes(frame)
    return str(poster)


def _attach_poster_metadata(db, media_id: int, poster_path: str | None) -> None:
    if not poster_path:
        return
    m = db.query(Media).filter(Media.id == media_id).first()
    if not m:
        return
    extras: dict = {}
    if m.classification_json:
        try:
            existing = json.loads(m.classification_json)
            if isinstance(existing, dict):
                extras = existing
        except Exception:
            pass
    extras["import_poster_path"] = poster_path
    m.classification_json = json.dumps(extras, ensure_ascii=False)
    db.commit()


def _job_skip_watermark(job: ImportJob) -> bool:
    if not job.result_json:
        return False
    try:
        parsed = json.loads(job.result_json)
        if isinstance(parsed, dict) and isinstance(parsed.get("params"), dict):
            return bool(parsed["params"].get("skip_watermark"))
    except Exception:
        pass
    return False


def run_import_job_sync(job_id: str) -> dict:
    """Celery entry: finalize staged bytes (local pool file or Telegram Saved Messages)."""
    db = SessionLocal()
    job: ImportJob | None = None
    try:
        job = db.query(ImportJob).filter(ImportJob.id == job_id).first()
        if not job:
            return {"ok": False, "error": "not_found", "job_id": job_id}
        if job.status == "cancelled":
            return {"ok": False, "error": "cancelled", "job_id": job_id}

        from app.services.local_media_storage import pool_import_local_enabled, store_pool_media_from_bytes

        pool_local = pool_import_local_enabled() and not job.saved_only
        update_job(db, job, status="processing", stage="finalize" if pool_local else "telegram")
        staging = Path(job.staging_path or "")
        if not staging.is_file():
            msg = "Staging file missing"
            update_job(db, job, status="failed", stage="failed", error_message=msg)
            return {"ok": False, "error": msg, "job_id": job_id}

        raw = staging.read_bytes()
        data, media_type = _prepare_bytes(job, raw)
        cap = (job.caption or "").strip() or None
        source = sanitize_import_source_url(job.source or "import:fast-job")
        if job.saved_only:
            from app.services.media_sniff import reject_html_or_tiny_payload

            reject_html_or_tiny_payload(data, url=source)
        poster_path = _maybe_write_poster(job, data, media_type)
        if poster_path:
            update_job(db, job, poster_path=poster_path)

        try:
            with skip_watermark_context(_job_skip_watermark(job)):
                if job.saved_only:

                    async def _saved_only(storage):
                        msg_id = await storage.save_to_saved_only(data, media_type, caption=cap)
                        return {"status": "saved_only", "telegram_message_id": msg_id}

                    result = _run_on_worker_loop(
                        asyncio.wait_for(
                            run_telegram_import_io(_saved_only),
                            timeout=import_telegram_timeout_s(),
                        )
                    )
                elif pool_local:
                    record = store_pool_media_from_bytes(
                        data,
                        media_type,
                        source,
                        job.pool_id,
                        db,
                        skip_watermark=_job_skip_watermark(job),
                    )
                    if record:
                        _attach_poster_metadata(db, record.id, poster_path)
                        result = {"status": "imported", "media_id": record.id}
                    else:
                        result = {"status": "skipped", "media_id": None}
                else:

                    async def _wrapped(storage):
                        record = await storage.store_from_bytes(
                            data,
                            media_type,
                            source,
                            job.pool_id,
                            db,
                            skip_watermark=_job_skip_watermark(job),
                        )
                        if record:
                            _attach_poster_metadata(db, record.id, poster_path)
                            return {"status": "imported", "media_id": record.id}
                        return {"status": "skipped", "media_id": None}

                    result = _run_on_worker_loop(
                        asyncio.wait_for(
                            run_telegram_import_io(_wrapped),
                            timeout=import_telegram_timeout_s(),
                        )
                    )
        except Exception:
            try:
                _run_on_worker_loop(reset_import_client())
            except Exception:
                logger.debug("reset admin client after import failure", exc_info=True)
            raise

        media_id = result.get("media_id")
        status = result.get("status", "done")
        terminal = status in ("imported", "saved_only", "skipped")
        update_job(
            db,
            job,
            status="done" if terminal else "failed",
            stage="done" if terminal else "failed",
            media_id=media_id,
            result=result,
        )
        if status == "imported" and media_id:
            from app.services.auto_tag_enrich import enqueue_auto_tag_enrich_if_enabled

            enqueue_auto_tag_enrich_if_enabled(int(media_id))

        cleanup_staging_files(job, keep_poster=True)
        return {"ok": True, "job_id": job_id, **result}
    except ImageProcessFailedError as e:
        msg = f"Telegram rejected this file: {e}"
        if job:
            update_job(db, job, status="failed", stage="failed", error_message=msg)
            cleanup_staging_files(job)
        return {"ok": False, "error": msg, "job_id": job_id}
    except asyncio.TimeoutError:
        msg = f"Telegram upload timed out after {import_telegram_timeout_s()}s"
        if job:
            update_job(db, job, status="failed", stage="failed", error_message=msg)
            cleanup_staging_files(job)
        return {"ok": False, "error": msg, "job_id": job_id}
    except Exception as e:
        msg = friendly_telegram_error(e)
        logger.warning("import job %s failed: %s", job_id, e, exc_info=True)
        if job:
            update_job(db, job, status="failed", stage="failed", error_message=msg)
            cleanup_staging_files(job)
        return {"ok": False, "error": msg, "job_id": job_id}
    finally:
        db.close()
