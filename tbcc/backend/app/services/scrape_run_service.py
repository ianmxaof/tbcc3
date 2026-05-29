"""Scrape run records, Redis lock (one scrape at a time), cron helpers."""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.database.session import SessionLocal
from app.models.scrape_run import ScrapeRun
from app.models.source import Source

logger = logging.getLogger(__name__)

SCRAPE_LOCK_KEY = "tbcc:scrape:lock"
SCRAPE_LOCK_TTL_SEC = 2 * 60 * 60
MEDIA_TYPES = frozenset({"both", "photos", "videos"})
CRON_RE = re.compile(r"^\S+\s+\S+\s+\S+\s+\S+\s+\S+$")

ERROR_CATALOG = {
    "lock_busy": {
        "message": "Another scrape is already running.",
        "fix": "Wait for the current scrape to finish. Only one scrape uses scraper.session at a time.",
    },
    "source_inactive": {
        "message": "Source is inactive.",
        "fix": "Open Automation → Ingest, edit the source, enable Active, then scrape again.",
    },
    "resolve_entity_failed": {
        "message": "Could not resolve Telegram channel.",
        "fix": "Join the channel with the scraper Telegram account, or use @username / t.me link instead of numeric id. Run setup-scraper-session.ps1 once to log in scraper.session.",
    },
    "scraper_session": {
        "message": "Telethon scraper session error.",
        "fix": "Run: cd tbcc/backend && python scripts/run_scrape_once.py <source_id> to log in scraper.session once.",
    },
    "celery_down": {
        "message": "Celery worker not processing scrape queue.",
        "fix": "Start TBCC-Celery (scrape queue) and Redis. Retry Scrape now.",
    },
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def normalize_media_types(raw: str | None) -> str:
    s = (raw or "both").strip().lower()
    if s in ("photo", "photos", "image", "images"):
        return "photos"
    if s in ("video", "videos"):
        return "videos"
    return "both" if s == "both" else "both"


def validate_schedule_cron(raw: str | None) -> str | None:
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    if not CRON_RE.match(s):
        raise ValueError('schedule_cron must be 5 fields, e.g. "0 6 * * *" (minute hour day month weekday)')
    try:
        from croniter import croniter

        croniter(s)
    except ImportError:
        pass
    except Exception as e:
        raise ValueError(f"Invalid cron expression: {e}") from e
    return s


def cron_due_now(cron_expr: str, now: datetime | None = None) -> bool:
    """True if this minute matches the cron schedule."""
    base = (now or utcnow()).replace(second=0, microsecond=0)
    try:
        from croniter import croniter

        if hasattr(croniter, "match"):
            return bool(croniter.match(cron_expr, base))
        itr = croniter(cron_expr, base)
        prev = itr.get_prev(datetime)
        return prev.replace(second=0, microsecond=0) == base
    except Exception:
        return False


def _redis_client():
    try:
        import redis

        url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        return redis.from_url(url, decode_responses=True)
    except Exception:
        return None


def acquire_scrape_lock(run_id: int) -> bool:
    r = _redis_client()
    if not r:
        return True
    try:
        return bool(r.set(SCRAPE_LOCK_KEY, str(run_id), nx=True, ex=SCRAPE_LOCK_TTL_SEC))
    except Exception as e:
        logger.warning("scrape lock acquire failed: %s", e)
        return True


def release_scrape_lock(run_id: int) -> None:
    r = _redis_client()
    if not r:
        return
    try:
        if r.get(SCRAPE_LOCK_KEY) == str(run_id):
            r.delete(SCRAPE_LOCK_KEY)
    except Exception as e:
        logger.warning("scrape lock release failed: %s", e)


def create_scrape_run(
    db: Session,
    source: Source,
    *,
    trigger: str = "manual",
    celery_task_id: str | None = None,
) -> ScrapeRun:
    run = ScrapeRun(
        source_id=source.id,
        source_name=source.name,
        pool_id=source.pool_id,
        trigger=trigger,
        status="queued",
        celery_task_id=celery_task_id,
        created_at=utcnow(),
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def mark_run_running(db: Session, run: ScrapeRun) -> None:
    run.status = "running"
    run.started_at = utcnow()
    db.commit()


def mark_run_skipped(db: Session, run: ScrapeRun, code: str, detail: str | None = None) -> None:
    cat = ERROR_CATALOG.get(code, {})
    summary = cat.get("message") or detail or code
    errors = [{"code": code, "message": summary, "fix": cat.get("fix"), "detail": detail}]
    run.status = "skipped"
    run.error_summary = summary
    run.errors_json = json.dumps(errors)
    run.errors_count = 1
    run.finished_at = utcnow()
    db.commit()


def finish_run_from_stats(db: Session, run: ScrapeRun, stats: dict) -> None:
    run.messages_scanned = int(stats.get("messages_scanned") or 0)
    run.stored = int(stats.get("stored") or 0)
    run.skipped_duplicate = int(stats.get("skipped_duplicate") or 0)
    run.skipped_media_type = int(stats.get("skipped_media_type") or 0)
    run.skipped_no_media = int(stats.get("skipped_no_media") or 0)
    run.errors_count = int(stats.get("errors_count") or 0)
    errors = stats.get("errors") or []
    if errors:
        run.errors_json = json.dumps(errors[:20])
        first = errors[0]
        run.error_summary = first.get("message") or first.get("code") or "Scrape had errors"
    elif run.stored == 0 and run.messages_scanned == 0:
        run.error_summary = stats.get("error_summary") or "No media found in scanned messages."
    else:
        run.error_summary = None
    run.status = "failed" if stats.get("fatal") else "done"
    if not stats.get("fatal") and run.errors_count and run.stored == 0 and run.messages_scanned == 0:
        run.status = "failed"
    run.finished_at = utcnow()
    db.commit()


def list_scrape_runs(db: Session, *, source_id: int | None = None, limit: int = 20) -> list[ScrapeRun]:
    q = db.query(ScrapeRun).order_by(ScrapeRun.id.desc())
    if source_id is not None:
        q = q.filter(ScrapeRun.source_id == source_id)
    return q.limit(min(max(limit, 1), 100)).all()


def scrape_run_to_dict(run: ScrapeRun) -> dict:
    errors = []
    if run.errors_json:
        try:
            errors = json.loads(run.errors_json)
        except Exception:
            errors = []
    fix_hint = None
    if errors and isinstance(errors[0], dict):
        fix_hint = errors[0].get("fix")
    return {
        "id": run.id,
        "source_id": run.source_id,
        "source_name": run.source_name,
        "pool_id": run.pool_id,
        "trigger": run.trigger,
        "status": run.status,
        "messages_scanned": run.messages_scanned,
        "stored": run.stored,
        "skipped_duplicate": run.skipped_duplicate,
        "skipped_media_type": run.skipped_media_type,
        "skipped_no_media": run.skipped_no_media,
        "errors_count": run.errors_count,
        "error_summary": run.error_summary,
        "errors": errors,
        "fix_hint": fix_hint,
        "media_library_url": f"/?status=pending&pool_id={run.pool_id or 1}",
        "celery_task_id": run.celery_task_id,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "created_at": run.created_at.isoformat() if run.created_at else None,
    }


def sources_due_for_cron(db: Session, now: datetime | None = None) -> list[Source]:
    now = now or utcnow()
    out: list[Source] = []
    q = db.query(Source).filter(
        Source.active == True,
        Source.schedule_enabled == True,
        Source.source_type == "telegram_channel",
        Source.schedule_cron.isnot(None),
    )
    for src in q.all():
        cron = (src.schedule_cron or "").strip()
        if not cron:
            continue
        if cron_due_now(cron, now):
            out.append(src)
    return out


def tick_scheduled_scrapes() -> dict:
    """Called from Celery beat — queue at most one due source if lock is free."""
    db = SessionLocal()
    try:
        due = sources_due_for_cron(db)
        if not due:
            return {"due": 0, "queued": 0}
        r = _redis_client()
        if r:
            try:
                if r.get(SCRAPE_LOCK_KEY):
                    return {"due": len(due), "queued": 0, "reason": "lock_busy"}
            except Exception:
                pass
        from app.workers.scraper_worker import run_scrape

        queued = 0
        for src in due[:1]:
            run_scrape.delay(int(src.id), trigger="cron")
            queued += 1
        return {"due": len(due), "queued": queued}
    finally:
        db.close()
