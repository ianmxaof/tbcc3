"""Background Celery worker for channel/forum-topic imports (no staged bytes)."""

from __future__ import annotations

import asyncio
import json
import logging
import os

from app.database.session import SessionLocal
from app.models.import_job import ImportJob
from app.services.import_job_runner import _run_on_worker_loop
from app.services.import_pipeline import update_job
from app.services.telegram_admin import (
    friendly_telegram_error,
    reset_import_client,
    run_telegram_import_io,
)

logger = logging.getLogger(__name__)


def channel_import_timeout_s(limit: int) -> int:
    """Per-job timeout: enough for large batches (150+ items with Telegram pacing)."""
    raw = (os.getenv("TBCC_CHANNEL_IMPORT_TIMEOUT_S") or "").strip()
    if raw:
        try:
            return max(120, int(raw))
        except ValueError:
            pass
    return max(900, min(7200, int(limit) * 20))


def run_channel_import_job_sync(job_id: str) -> dict:
    db = SessionLocal()
    job: ImportJob | None = None
    params: dict = {}
    try:
        job = db.query(ImportJob).filter(ImportJob.id == job_id).first()
        if not job:
            return {"ok": False, "error": "not_found", "job_id": job_id}
        if (job.job_kind or "bytes") != "channel":
            return {"ok": False, "error": "wrong_job_kind", "job_id": job_id}
        if job.status == "cancelled":
            return {"ok": False, "error": "cancelled", "job_id": job_id}

        if job.result_json:
            try:
                parsed = json.loads(job.result_json)
                if isinstance(parsed, dict):
                    params = parsed.get("params") if isinstance(parsed.get("params"), dict) else parsed
            except Exception:
                params = {}

        channel = str(params.get("channel") or job.source or "").strip()
        if not channel:
            msg = "Missing channel in job params"
            update_job(db, job, status="failed", stage="failed", error_message=msg)
            return {"ok": False, "error": msg, "job_id": job_id}

        limit = int(params.get("limit") or 50)
        media_types = str(params.get("media_types") or job.media_type or "both")
        message_thread_id = params.get("message_thread_id")
        if message_thread_id is not None and message_thread_id != "":
            message_thread_id = int(message_thread_id)
        else:
            message_thread_id = None
        source_label = str(params.get("source_label") or job.source or f"telegram:{channel}").strip()

        update_job(db, job, status="processing", stage="telegram")

        async def _import(storage):
            return await storage.import_from_telegram_channel(
                channel,
                job.pool_id,
                source_label,
                db,
                limit=limit,
                media_types=media_types,
                message_thread_id=message_thread_id,
            )

        timeout = channel_import_timeout_s(limit)
        try:
            result = _run_on_worker_loop(asyncio.wait_for(run_telegram_import_io(_import), timeout=timeout))
        except Exception:
            try:
                _run_on_worker_loop(reset_import_client())
            except Exception:
                logger.debug("reset admin client after channel import failure", exc_info=True)
            raise

        update_job(db, job, status="done", stage="done", result=result)
        return {"ok": True, "job_id": job_id, "status": "done", **result}
    except asyncio.TimeoutError:
        msg = f"Channel import timed out after {channel_import_timeout_s(int((params or {}).get('limit') or 50))}s"
        if job:
            update_job(db, job, status="failed", stage="failed", error_message=msg)
        return {"ok": False, "error": msg, "job_id": job_id}
    except Exception as e:
        msg = friendly_telegram_error(e)
        logger.warning("channel import job %s failed: %s", job_id, e, exc_info=True)
        if job:
            update_job(db, job, status="failed", stage="failed", error_message=msg)
        return {"ok": False, "error": msg, "job_id": job_id}
    finally:
        db.close()
