"""Poll and list async import jobs (fast import pipeline)."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.import_job import ImportJob
from app.services.import_pipeline import (
    TERMINAL_STATUSES,
    cancel_import_job,
    job_to_public_dict,
    prune_old_jobs,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/jobs/{job_id}")
def get_import_job(job_id: str, db: Session = Depends(get_db)):
    job = db.query(ImportJob).filter(ImportJob.id == job_id).first()
    if not job:
        return {"error": "not_found", "job_id": job_id}
    body = job_to_public_dict(job)
    body["poll_url"] = f"/import/jobs/{job_id}"
    return body


@router.get("/jobs")
def list_import_jobs(
    active: bool = Query(False, description="Only non-terminal jobs from the last 2 hours"),
    limit: int = Query(40, ge=1, le=200),
    db: Session = Depends(get_db),
):
    prune_old_jobs(db)
    q = db.query(ImportJob).order_by(ImportJob.updated_at.desc())
    if active:
        cutoff = datetime.utcnow() - timedelta(hours=2)
        q = q.filter(
            ImportJob.updated_at >= cutoff,
            ~ImportJob.status.in_(list(TERMINAL_STATUSES)),
        )
    rows = q.limit(limit).all()
    return {"jobs": [job_to_public_dict(j) for j in rows]}


@router.post("/jobs/{job_id}/cancel")
def post_cancel_import_job(job_id: str, db: Session = Depends(get_db)):
    return cancel_import_job(db, job_id)


@router.get("/queue/status")
def import_queue_status(db: Session = Depends(get_db)):
    """Celery telegram-queue depth + DB import jobs still in flight."""
    cutoff = datetime.utcnow() - timedelta(hours=2)
    db_active = (
        db.query(ImportJob)
        .filter(
            ImportJob.updated_at >= cutoff,
            ~ImportJob.status.in_(list(TERMINAL_STATUSES)),
        )
        .count()
    )
    telegram_active = 0
    telegram_reserved = 0
    workers_seen: list[str] = []
    celery_ok = False
    try:
        from app.workers.celery_app import celery

        insp = celery.control.inspect(timeout=2.0)
        if insp:
            active_map = insp.active() or {}
            reserved_map = insp.reserved() or {}
            celery_ok = True
            for worker_name, tasks in active_map.items():
                workers_seen.append(str(worker_name))
                for t in tasks or []:
                    name = str(t.get("name") or "")
                    if "import_telegram" in name or "process_import_job" in name:
                        telegram_active += 1
            for _worker, tasks in reserved_map.items():
                for t in tasks or []:
                    name = str(t.get("name") or "")
                    if "import_telegram" in name or "process_import_job" in name:
                        telegram_reserved += 1
    except Exception as e:
        logger.debug("import queue inspect failed: %s", e)

    return {
        "ok": True,
        "celery_reachable": celery_ok,
        "db_active_import_jobs": db_active,
        "telegram_tasks_active": telegram_active,
        "telegram_tasks_reserved": telegram_reserved,
        "workers": workers_seen[:12],
    }
