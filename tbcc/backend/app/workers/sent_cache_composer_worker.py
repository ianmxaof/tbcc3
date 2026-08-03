"""Celery: SENT CACHE album composer after /deposit."""

from __future__ import annotations

import logging
from typing import Any

from app.workers.celery_app import celery

logger = logging.getLogger(__name__)


@celery.task(name="app.workers.sent_cache_composer_worker.compose_sent_cache_albums_task")
def compose_sent_cache_albums_task(
    *,
    job_id: str,
    network_key: str,
    media_ids: list[int],
    pool_id: int | None,
    storage_thread_id: int | None,
    moved_items: list[dict[str, Any]] | None = None,
    skip_cache_rebundle: bool = False,
):
    from app.database.session import SessionLocal
    from app.models.import_job import ImportJob
    from app.services.sent_cache_composer import (
        compose_sent_cache_albums_sync,
        notify_composer_bot,
    )

    db = SessionLocal()
    try:
        report = compose_sent_cache_albums_sync(
            db,
            network_key=network_key,
            media_ids=media_ids,
            pool_id=pool_id,
            moved_items=moved_items,
            skip_cache_rebundle=skip_cache_rebundle,
        )
        if storage_thread_id:
            notify = notify_composer_bot(
                storage_thread_id=int(storage_thread_id),
                network_key=network_key,
                report=report,
            )
            report["composer_notify"] = notify

        job = db.query(ImportJob).filter(ImportJob.id == job_id).first()
        if job:
            import json

            try:
                parsed = json.loads(job.result_json) if job.result_json else {}
            except (json.JSONDecodeError, TypeError):
                parsed = {}
            if isinstance(parsed, dict) and isinstance(parsed.get("params"), dict):
                inner = parsed.get("result") if isinstance(parsed.get("result"), dict) else {}
                inner = dict(inner)
                inner["cache_composer"] = report
                parsed["result"] = inner
            elif isinstance(parsed, dict):
                parsed = dict(parsed)
                parsed["cache_composer"] = report
            else:
                parsed = {"cache_composer": report}
            job.result_json = json.dumps(parsed, ensure_ascii=False)
            db.commit()

        logger.info(
            "sent cache composer job=%s lane=%s albums=%s",
            job_id,
            network_key,
            report.get("albums_built"),
        )
        return report
    finally:
        db.close()
