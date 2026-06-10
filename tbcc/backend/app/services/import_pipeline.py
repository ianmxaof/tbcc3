"""
Fast import pipeline: stage bytes on disk, return job id immediately, process Telegram upload on Celery telegram queue.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.import_job import ImportJob, new_import_job_id

logger = logging.getLogger(__name__)

TERMINAL_STATUSES = frozenset({"done", "failed", "skipped", "cancelled"})


def tbcc_run_dir() -> Path:
    root = Path(__file__).resolve().parent.parent.parent.parent
    run = root / ".tbcc-run"
    run.mkdir(parents=True, exist_ok=True)
    return run


def import_staging_dir() -> Path:
    d = tbcc_run_dir() / "import-staging"
    d.mkdir(parents=True, exist_ok=True)
    return d


def fast_import_enabled() -> bool:
    return (os.getenv("TBCC_FAST_IMPORT") or "1").strip().lower() not in ("0", "false", "no", "off")


def import_max_bytes() -> int:
    raw = (os.getenv("TBCC_IMPORT_MAX_BYTES") or "524288000").strip()
    try:
        return max(1, int(raw))
    except ValueError:
        return 524_288_000


def import_telegram_timeout_s() -> int:
    raw = (os.getenv("TBCC_IMPORT_TELEGRAM_TIMEOUT_S") or "600").strip()
    try:
        return max(30, int(raw))
    except ValueError:
        return 600


def classify_use_staged_bytes() -> bool:
    return (os.getenv("TBCC_CLASSIFY_USE_STAGED_BYTES") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def _now() -> datetime:
    return datetime.utcnow()


def job_to_public_dict(job: ImportJob) -> dict:
    out = {
        "job_id": job.id,
        "job_kind": getattr(job, "job_kind", None) or "bytes",
        "status": job.status,
        "stage": job.stage,
        "pool_id": job.pool_id,
        "saved_only": bool(job.saved_only),
        "byte_size": job.byte_size,
        "media_id": job.media_id,
        "extension_job_id": job.extension_job_id,
        "error": job.error_message,
        "created_at": job.created_at.isoformat() + "Z" if job.created_at else None,
        "updated_at": job.updated_at.isoformat() + "Z" if job.updated_at else None,
    }
    if job.result_json:
        try:
            parsed = json.loads(job.result_json)
            if isinstance(parsed, dict) and isinstance(parsed.get("params"), dict):
                out["params"] = parsed["params"]
                if parsed.get("result") is not None:
                    out["result"] = parsed["result"]
            else:
                out["result"] = parsed
        except Exception:
            pass
    return out


def update_job(
    db: Session,
    job: ImportJob,
    *,
    status: str | None = None,
    stage: str | None = None,
    media_id: int | None = None,
    error_message: str | None = None,
    result: dict | None = None,
    celery_task_id: str | None = None,
    poster_path: str | None = None,
) -> ImportJob:
    if status is not None:
        job.status = status
    if stage is not None:
        job.stage = stage
    if media_id is not None:
        job.media_id = media_id
    if error_message is not None:
        job.error_message = error_message[:4000] if error_message else None
    if celery_task_id is not None:
        job.celery_task_id = celery_task_id
    if poster_path is not None:
        job.poster_path = poster_path
    if result is not None:
        if job.result_json:
            try:
                existing = json.loads(job.result_json)
                if isinstance(existing, dict) and isinstance(existing.get("params"), dict):
                    existing["result"] = result
                    job.result_json = json.dumps(existing, ensure_ascii=False)
                else:
                    job.result_json = json.dumps(result, ensure_ascii=False)
            except Exception:
                job.result_json = json.dumps(result, ensure_ascii=False)
        else:
            job.result_json = json.dumps(result, ensure_ascii=False)
    job.updated_at = _now()
    db.commit()
    db.refresh(job)
    return job


def create_staged_import_job(
    db: Session,
    *,
    file_bytes: bytes,
    pool_id: int,
    saved_only: bool,
    source: str,
    caption: str | None,
    filename: str | None,
    media_type: str,
    extension_job_id: str | None = None,
    skip_watermark: bool = False,
) -> ImportJob:
    size = len(file_bytes)
    if size > import_max_bytes():
        raise ValueError(
            f"File too large ({size} bytes). Max is {import_max_bytes()} (TBCC_IMPORT_MAX_BYTES)."
        )
    job_id = new_import_job_id()
    staging = import_staging_dir() / f"{job_id}.bin"
    staging.write_bytes(file_bytes)
    job = ImportJob(
        id=job_id,
        job_kind="bytes",
        status="queued",
        stage="stored",
        pool_id=int(pool_id),
        saved_only=bool(saved_only),
        source=(source or "")[:512] or None,
        caption=caption,
        filename=(filename or "")[:256] or None,
        media_type=media_type,
        byte_size=size,
        staging_path=str(staging),
        extension_job_id=(extension_job_id or "")[:64] or None,
        result_json=json.dumps({"params": {"skip_watermark": bool(skip_watermark)}}, ensure_ascii=False)
        if skip_watermark
        else None,
        created_at=_now(),
        updated_at=_now(),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def create_channel_import_job(
    db: Session,
    *,
    channel: str,
    pool_id: int,
    limit: int,
    media_types: str,
    message_thread_id: int | None = None,
    source_label: str,
    topic_title: str | None = None,
) -> ImportJob:
    job_id = new_import_job_id()
    params = {
        "channel": channel,
        "limit": int(limit),
        "media_types": media_types,
        "message_thread_id": message_thread_id,
        "source_label": source_label,
        "topic_title": (topic_title or "").strip() or None,
    }
    job = ImportJob(
        id=job_id,
        job_kind="channel",
        status="queued",
        stage="queued",
        pool_id=int(pool_id),
        saved_only=False,
        source=(source_label or "")[:512] or None,
        media_type=media_types,
        byte_size=0,
        result_json=json.dumps({"params": params}, ensure_ascii=False),
        created_at=_now(),
        updated_at=_now(),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def enqueue_channel_import_job(job_id: str) -> str | None:
    from app.workers.import_telegram_worker import process_import_job

    async_result = process_import_job.apply_async(args=[job_id], queue="telegram")
    return async_result.id if async_result else None


def enqueue_import_job_processing(job_id: str) -> str | None:
    from app.workers.import_telegram_worker import process_import_job

    async_result = process_import_job.apply_async(args=[job_id], queue="telegram")
    return async_result.id if async_result else None


def cleanup_staging_files(job: ImportJob, *, keep_poster: bool = False) -> None:
    for path in (job.staging_path,):
        if not path:
            continue
        try:
            Path(path).unlink(missing_ok=True)
        except OSError as e:
            logger.debug("staging unlink %s: %s", path, e)
    if not keep_poster and job.poster_path:
        try:
            Path(job.poster_path).unlink(missing_ok=True)
        except OSError as e:
            logger.debug("poster unlink %s: %s", job.poster_path, e)


def prune_old_jobs(db: Session, max_age_hours: int = 48) -> int:
    cutoff = _now() - timedelta(hours=max_age_hours)
    rows = (
        db.query(ImportJob)
        .filter(ImportJob.updated_at < cutoff, ImportJob.status.in_(list(TERMINAL_STATUSES)))
        .limit(200)
        .all()
    )
    n = 0
    for job in rows:
        cleanup_staging_files(job, keep_poster=False)
        db.delete(job)
        n += 1
    if n:
        db.commit()
    return n


def read_staged_bytes(job: ImportJob) -> bytes | None:
    if not job.staging_path:
        return None
    p = Path(job.staging_path)
    if not p.is_file():
        return None
    return p.read_bytes()


def read_poster_bytes(job: ImportJob) -> bytes | None:
    if not job.poster_path:
        return None
    p = Path(job.poster_path)
    if not p.is_file():
        return None
    return p.read_bytes()


def cancel_import_job(db: Session, job_id: str) -> dict:
    """Mark job cancelled, revoke Celery task if queued/running, drop staging files."""
    job = db.query(ImportJob).filter(ImportJob.id == job_id).first()
    if not job:
        return {"ok": False, "error": "not_found", "job_id": job_id}
    if job.status in TERMINAL_STATUSES:
        return {
            "ok": False,
            "error": "not_cancellable",
            "job_id": job_id,
            "status": job.status,
        }
    if job.celery_task_id:
        try:
            from app.workers.celery_app import celery

            celery.control.revoke(job.celery_task_id, terminate=True)
        except Exception as e:
            logger.warning("Celery revoke failed for %s: %s", job.celery_task_id, e)
    update_job(
        db,
        job,
        status="cancelled",
        stage="cancelled",
        error_message="Cancelled by user",
    )
    cleanup_staging_files(job)
    return {"ok": True, "job_id": job_id, "status": "cancelled"}
