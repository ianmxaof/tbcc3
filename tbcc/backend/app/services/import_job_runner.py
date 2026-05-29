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
from app.services.telegram_admin import friendly_telegram_error, run_telegram_io
from app.services.tbcc_media_url import sanitize_import_source_url

logger = logging.getLogger(__name__)


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


def run_import_job_sync(job_id: str) -> dict:
    """Celery entry: upload staged bytes to Telegram and finalize job row."""
    db = SessionLocal()
    job: ImportJob | None = None
    try:
        job = db.query(ImportJob).filter(ImportJob.id == job_id).first()
        if not job:
            return {"ok": False, "error": "not_found", "job_id": job_id}
        if job.status == "cancelled":
            return {"ok": False, "error": "cancelled", "job_id": job_id}

        update_job(db, job, status="processing", stage="telegram")
        staging = Path(job.staging_path or "")
        if not staging.is_file():
            msg = "Staging file missing"
            update_job(db, job, status="failed", stage="failed", error_message=msg)
            return {"ok": False, "error": msg, "job_id": job_id}

        raw = staging.read_bytes()
        data, media_type = _prepare_bytes(job, raw)
        cap = (job.caption or "").strip() or None
        source = sanitize_import_source_url(job.source or "import:fast-job")
        poster_path = _maybe_write_poster(job, data, media_type)
        if poster_path:
            update_job(db, job, poster_path=poster_path)

        async def _wrapped(storage):
            if job.saved_only:
                await storage.save_to_saved_only(data, media_type, caption=cap)
                return {"status": "saved_only"}
            record = await storage.store_from_bytes(data, media_type, source, job.pool_id, db)
            if record:
                _attach_poster_metadata(db, record.id, poster_path)
                return {"status": "imported", "media_id": record.id}
            return {"status": "skipped", "media_id": None}

        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(
                asyncio.wait_for(
                    run_telegram_io(_wrapped),
                    timeout=import_telegram_timeout_s(),
                )
            )
        finally:
            loop.close()
            asyncio.set_event_loop(None)

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
