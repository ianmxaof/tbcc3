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


def channel_import_timeout_s(
    limit: int,
    *,
    media_types: str | None = None,
    index_only: bool = False,
    sent_cache: bool = False,
) -> int:
    """Per-job timeout: enough for video downloads (limit × per-item budget + lock wait)."""
    lim = max(1, int(limit))
    lock_budget = int(os.getenv("TBCC_CHANNEL_IMPORT_LOCK_BUDGET_S") or "360")
    if index_only:
        per_item = int(os.getenv("TBCC_CHANNEL_IMPORT_SEC_PER_INDEX") or "3")
        if sent_cache:
            per_item += int(os.getenv("TBCC_STORAGE_SENT_CACHE_SEC_PER_ITEM") or "2")
        base = max(120, min(1800, lim * per_item + 60))
        return base + max(0, lock_budget)
    mt = (media_types or "videos").strip().lower()
    raw = (os.getenv("TBCC_CHANNEL_IMPORT_TIMEOUT_S") or "").strip()
    if raw:
        try:
            base = max(120, int(raw))
        except ValueError:
            base = max(900, min(10800, lim * 90))
    else:
        per_photo = int(os.getenv("TBCC_CHANNEL_IMPORT_SEC_PER_PHOTO") or "45")
        per_video = int(os.getenv("TBCC_CHANNEL_IMPORT_SEC_PER_VIDEO") or "120")
        if mt == "photos":
            per_item = per_photo
        elif mt == "videos":
            per_item = per_video
        else:
            per_item = max(per_photo, per_video)
        base = max(900, min(10800, lim * per_item))
    lock_budget = int(os.getenv("TBCC_CHANNEL_IMPORT_LOCK_BUDGET_S") or "360")
    return base + max(0, lock_budget)


MAX_LOOP_BUSY_DEFERRALS = 6


def _is_worker_loop_busy(exc: BaseException) -> bool:
    """Another coroutine already owns this thread's event loop — transient, not a bad job."""
    text = str(exc or "").lower()
    return "another loop is running" in text or "event loop is already running" in text


def _loop_busy_backoff_s(deferrals: int) -> int:
    raw = (os.getenv("TBCC_IMPORT_LOOP_BUSY_BACKOFF_S") or "30").strip()
    try:
        base = max(5, min(600, int(raw)))
    except ValueError:
        base = 30
    return min(base * max(1, deferrals), 900)


def _defer_channel_import(db, job: ImportJob, params: dict, *, error: BaseException) -> dict:
    """Re-queue instead of burning the job — the loop frees up when the current task finishes."""
    from app.services.import_pipeline import enqueue_channel_import_job

    deferrals = int((params or {}).get("loop_busy_deferrals") or 0) + 1
    if deferrals > MAX_LOOP_BUSY_DEFERRALS:
        msg = (
            f"Import worker event loop stayed busy across {MAX_LOOP_BUSY_DEFERRALS} retries. "
            "Check for a long-running Telegram upload on the telegram queue."
        )
        logger.warning("channel import job %s giving up: %s", job.id, error)
        update_job(db, job, status="failed", stage="failed", error_message=msg)
        return {"ok": False, "error": msg, "job_id": job.id}

    merged = dict(params or {})
    merged["loop_busy_deferrals"] = deferrals
    countdown = _loop_busy_backoff_s(deferrals)
    update_job(db, job, status="queued", stage="queued", result={"params": merged})
    try:
        enqueue_channel_import_job(str(job.id), countdown=countdown)
    except Exception:
        logger.exception("channel import re-enqueue failed job=%s", job.id)
        update_job(db, job, status="failed", stage="failed", error_message="re-enqueue failed")
        return {"ok": False, "error": "re-enqueue failed", "job_id": job.id}
    logger.info(
        "channel import job %s deferred (%s/%s) — worker loop busy; retry in %ss",
        job.id,
        deferrals,
        MAX_LOOP_BUSY_DEFERRALS,
        countdown,
    )
    return {"ok": True, "deferred": True, "job_id": job.id, "retry_in_s": countdown}


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
        apply_watermark = bool(params.get("apply_watermark"))
        index_only = bool(params.get("index_only"))
        network_key = str(params.get("network_key") or "").strip() or None
        sent_cache = bool(params.get("sent_cache"))
        auto_pipe = bool(params.get("auto_pipe"))
        qa_review_only = bool(params.get("qa_review_only"))
        raw_ids = params.get("message_ids")
        message_ids: list[int] | None = None
        if isinstance(raw_ids, list) and raw_ids:
            message_ids = [int(x) for x in raw_ids if int(x) > 0]

        update_job(db, job, status="processing", stage="telegram")

        async def _import(storage):
            result = await storage.import_from_telegram_channel(
                channel,
                job.pool_id,
                source_label,
                db,
                limit=limit,
                media_types=media_types,
                message_thread_id=message_thread_id,
                apply_watermark=apply_watermark,
                index_only=index_only,
                message_ids=message_ids,
            )
            if sent_cache and int(result.get("stored") or 0) > 0:
                from app.services.storage_sent_cache import move_deposit_batch_to_sent_cache

                update_job(db, job, status="processing", stage="sent_cache")
                cache_body = await move_deposit_batch_to_sent_cache(
                    storage,
                    db,
                    stored_messages=list(result.get("stored_messages") or []),
                    network_key=network_key,
                    hub_ident=channel,
                    force_flush=True,
                )
                result["sent_cache"] = cache_body
                if int(cache_body.get("moved") or 0) > 0:
                    media_ids = [
                        int(r.get("media_id"))
                        for r in (result.get("stored_messages") or [])
                        if isinstance(r, dict) and r.get("media_id")
                    ]
                    try:
                        from app.services.export_flywheel_service import emit_export_intent

                        emit_export_intent(
                            db,
                            pool_id=int(job.pool_id) if job.pool_id else None,
                            network_key=network_key,
                            media_ids=media_ids,
                            export_source="cache_deposit",
                        )
                    except Exception:
                        logger.debug("export flywheel deposit trigger skipped", exc_info=True)
                    try:
                        from app.services.sent_cache_composer import enqueue_cache_composer_after_deposit

                        enqueue_cache_composer_after_deposit(
                            job_id=str(job.id),
                            network_key=network_key or "",
                            media_ids=media_ids,
                            pool_id=int(job.pool_id) if job.pool_id else None,
                            storage_thread_id=message_thread_id,
                            moved_items=list(cache_body.get("moved_items") or []),
                            skip_cache_rebundle=int(cache_body.get("albums_posted") or 0) > 0,
                        )
                    except Exception:
                        logger.debug("sent cache composer enqueue skipped", exc_info=True)
            dup_lane_ids = list(result.get("duplicate_lane_message_ids") or [])
            if (
                sent_cache
                and dup_lane_ids
                and message_thread_id is not None
            ):
                from app.services.storage_sent_cache import (
                    evict_lane_messages,
                    storage_deposit_lane_evict_enabled,
                )

                if storage_deposit_lane_evict_enabled():
                    update_job(db, job, status="processing", stage="lane_evict")
                    evict_body = await evict_lane_messages(storage, channel, dup_lane_ids)
                    result["lane_evict"] = evict_body
            if auto_pipe:
                from app.services.intake_scheduler import mark_lane_run

                if network_key:
                    mark_lane_run(network_key)
                result["auto_pipe"] = True
            if qa_review_only and network_key:
                from app.models.media import Media
                from app.services.quarantine_batch_review import (
                    flush_lane_quarantine_buffer,
                    queue_lane_quarantine_media,
                )

                queued = 0
                for row in result.get("stored_messages") or []:
                    if not isinstance(row, dict):
                        continue
                    mid = row.get("media_id")
                    if not mid:
                        continue
                    media = db.query(Media).filter(Media.id == int(mid)).first()
                    if media and (media.status or "") != "quarantine":
                        media.status = "quarantine"
                    queue_lane_quarantine_media(int(mid), network_key)
                    queued += 1
                if queued:
                    db.commit()
                    flush_lane_quarantine_buffer(db, network_key, force=False)
                result["qa_review_only"] = True
                result["qa_review_queued"] = queued
            return result

        timeout = channel_import_timeout_s(
            limit,
            media_types=media_types,
            index_only=index_only,
            sent_cache=sent_cache,
        )
        try:
            result = _run_on_worker_loop(asyncio.wait_for(run_telegram_import_io(_import), timeout=timeout))
        except Exception:
            try:
                _run_on_worker_loop(reset_import_client())
            except Exception:
                logger.debug("reset admin client after channel import failure", exc_info=True)
            raise

        update_job(db, job, status="done", stage="done", result=result)
        try:
            from app.services.telegram_admin import reset_admin_client, reset_import_client

            async def _release_both():
                await reset_import_client()
                await reset_admin_client()
                await asyncio.sleep(0.5)

            _run_on_worker_loop(_release_both())
        except Exception:
            logger.debug("post-import session release before mirror handoff", exc_info=True)
        return {"ok": True, "job_id": job_id, "status": "done", **result}
    except asyncio.TimeoutError:
        mt = str((params or {}).get("media_types") or "videos")
        budget = channel_import_timeout_s(int((params or {}).get("limit") or 50), media_types=mt)
        msg = (
            f"Channel import timed out after {budget}s "
            f"(limit={int((params or {}).get('limit') or 50)}, media={mt}). "
            "Large videos need more time — retry with a smaller /deposit count, "
            "or raise TBCC_CHANNEL_IMPORT_SEC_PER_VIDEO in tbcc/.env."
        )
        if job:
            update_job(db, job, status="failed", stage="failed", error_message=msg)
        return {"ok": False, "error": msg, "job_id": job_id}
    except RuntimeError as e:
        if job and _is_worker_loop_busy(e):
            return _defer_channel_import(db, job, params, error=e)
        msg = friendly_telegram_error(e)
        logger.warning("channel import job %s failed: %s", job_id, e, exc_info=True)
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
