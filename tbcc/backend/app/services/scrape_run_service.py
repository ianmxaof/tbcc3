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
SCRAPE_CANCEL_PREFIX = "tbcc:scrape:cancel:"
MEDIA_TYPES = frozenset({"both", "photos", "videos"})
CRON_RE = re.compile(r"^\S+\s+\S+\s+\S+\s+\S+\s+\S+$")
ACTIVE_RUN_STATUSES = frozenset({"queued", "running"})
TERMINAL_RUN_STATUSES = frozenset({"done", "failed", "skipped", "cancelled"})

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
    "forward_restricted": {
        "message": "Channel forbids forwarding — auto-skipped.",
        "fix": "Channel intel marks forward-disabled sources inactive. Re-enable only if the channel policy changed.",
    },
    "user_cancelled": {
        "message": "Scrape cancelled from transport.",
        "fix": "Queue another scrape or enable schedule to resume autonomous runs.",
    },
    "user_skipped": {
        "message": "Scrape skipped — advancing queue.",
        "fix": "Next queued/due source will run when the scrape lock is free.",
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


def force_release_scrape_lock() -> str | None:
    """Clear scrape lock regardless of holder. Returns previous holder run id if any."""
    r = _redis_client()
    if not r:
        return None
    try:
        prev = r.get(SCRAPE_LOCK_KEY)
        r.delete(SCRAPE_LOCK_KEY)
        return str(prev) if prev else None
    except Exception as e:
        logger.warning("scrape lock force release failed: %s", e)
        return None


def get_scrape_lock_holder() -> int | None:
    r = _redis_client()
    if not r:
        return None
    try:
        raw = r.get(SCRAPE_LOCK_KEY)
        return int(raw) if raw and str(raw).isdigit() else None
    except Exception:
        return None


def request_scrape_cancel(run_id: int) -> None:
    r = _redis_client()
    if not r:
        return
    try:
        r.set(f"{SCRAPE_CANCEL_PREFIX}{int(run_id)}", "1", ex=SCRAPE_LOCK_TTL_SEC)
    except Exception as e:
        logger.warning("scrape cancel flag set failed: %s", e)


def is_scrape_cancel_requested(run_id: int) -> bool:
    r = _redis_client()
    if not r:
        return False
    try:
        return bool(r.get(f"{SCRAPE_CANCEL_PREFIX}{int(run_id)}"))
    except Exception:
        return False


def clear_scrape_cancel(run_id: int) -> None:
    r = _redis_client()
    if not r:
        return
    try:
        r.delete(f"{SCRAPE_CANCEL_PREFIX}{int(run_id)}")
    except Exception:
        pass


def mark_run_cancelled(db: Session, run: ScrapeRun, code: str = "user_cancelled") -> None:
    cat = ERROR_CATALOG.get(code, {})
    summary = cat.get("message") or code
    errors = [{"code": code, "message": summary, "fix": cat.get("fix")}]
    run.status = "cancelled"
    run.error_summary = summary
    run.errors_json = json.dumps(errors)
    run.errors_count = 1
    run.finished_at = utcnow()
    db.commit()


def cancel_scrape_run(
    db: Session,
    run_id: int,
    *,
    code: str = "user_cancelled",
    revoke_celery: bool = True,
) -> dict:
    """Cancel a queued/running scrape: flag worker, revoke Celery task, free lock, mark cancelled."""
    run = db.query(ScrapeRun).filter(ScrapeRun.id == run_id).first()
    if not run:
        raise ValueError("scrape run not found")
    if run.status in TERMINAL_RUN_STATUSES:
        return {"ok": True, "run_id": run.id, "status": run.status, "already_terminal": True}

    request_scrape_cancel(run.id)
    if revoke_celery and run.celery_task_id:
        try:
            from app.workers.celery_app import celery

            celery.control.revoke(run.celery_task_id, terminate=True, signal="SIGTERM")
        except Exception as e:
            logger.warning("celery revoke failed for %s: %s", run.celery_task_id, e)

    release_scrape_lock(run.id)
    # If this run held a stale lock under a different id, clear anyway when cancelling active.
    holder = get_scrape_lock_holder()
    if holder == run.id:
        force_release_scrape_lock()

    mark_run_cancelled(db, run, code=code)
    clear_scrape_cancel(run.id)
    return {"ok": True, "run_id": run.id, "status": "cancelled", "code": code}


def skip_active_scrape(db: Session, *, queue_next: bool = True) -> dict:
    """Cancel the current active scrape and optionally enqueue the next due cron source."""
    active = (
        db.query(ScrapeRun)
        .filter(ScrapeRun.status.in_(tuple(ACTIVE_RUN_STATUSES)))
        .order_by(ScrapeRun.id.desc())
        .first()
    )
    cancelled = None
    if active:
        cancelled = cancel_scrape_run(db, active.id, code="user_skipped")
    else:
        # Stale lock with no active DB row — free the lane.
        force_release_scrape_lock()

    queued_next = None
    if queue_next:
        due = sources_due_for_cron(db)
        # Prefer next due that isn't the cancelled source.
        cancelled_src = int(active.source_id) if active and active.source_id else None
        candidates = [s for s in due if cancelled_src is None or int(s.id) != cancelled_src]
        if not candidates:
            # Fall back: next active scheduled source by id after cancelled.
            q = (
                db.query(Source)
                .filter(
                    Source.active == True,  # noqa: E712
                    Source.schedule_enabled == True,  # noqa: E712
                    Source.source_type == "telegram_channel",
                )
                .order_by(Source.id.asc())
            )
            rows = list(q.all())
            if cancelled_src is not None:
                after = [s for s in rows if int(s.id) > cancelled_src]
                candidates = after or [s for s in rows if int(s.id) != cancelled_src]
            else:
                candidates = rows
        if candidates:
            from app.workers.scraper_worker import run_scrape

            nxt = candidates[0]
            run = create_scrape_run(db, nxt, trigger="manual")
            async_result = run_scrape.delay(int(nxt.id), "manual", run.id)
            run.celery_task_id = async_result.id
            db.commit()
            queued_next = {
                "source_id": int(nxt.id),
                "source_name": nxt.name,
                "run_id": run.id,
                "celery_task_id": async_result.id,
            }

    return {
        "ok": True,
        "cancelled": cancelled,
        "queued_next": queued_next,
    }


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
    if is_scrape_cancel_requested(run.id) or run.status == "cancelled":
        if run.status != "cancelled":
            mark_run_cancelled(db, run, "user_cancelled")
        clear_scrape_cancel(run.id)
        return
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
    if int(stats.get("skipped_forward_restricted") or 0) > 0 and run.stored == 0:
        run.status = "skipped"
        if not run.error_summary:
            run.error_summary = stats.get("error_summary") or "forward_restricted"
    elif stats.get("fatal"):
        run.status = "failed"
    else:
        run.status = "done"
    if (
        run.status == "done"
        and run.errors_count
        and run.stored == 0
        and run.messages_scanned == 0
    ):
        run.status = "failed"
    run.finished_at = utcnow()
    db.commit()


def list_scrape_runs(db: Session, *, source_id: int | None = None, limit: int = 20) -> list[ScrapeRun]:
    q = db.query(ScrapeRun).order_by(ScrapeRun.id.desc())
    if source_id is not None:
        q = q.filter(ScrapeRun.source_id == source_id)
    return q.limit(min(max(limit, 1), 100)).all()


def scrape_run_to_dict(run: ScrapeRun) -> dict:
    is_link = int(run.source_id or 0) == 0 and (run.source_name or "").startswith("LINK:")
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
        "run_kind": "link" if is_link else "media",
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
        "media_library_url": "/scheduler/bots" if is_link else f"/?status=pending&pool_id={run.pool_id or 1}",
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


def scrape_transport_overview(db: Session) -> dict:
    """Compact transport snapshot for Automation → Ingest."""
    from app.models.content_pool import ContentPool
    from app.models.scrape_channel_profile import ScrapeChannelProfile
    from app.services.scrape_channel_intel import public_telegram_url

    sources = (
        db.query(Source)
        .filter(Source.source_type == "telegram_channel")
        .order_by(Source.id.asc())
        .all()
    )
    pool_names = {int(p.id): (p.name or f"Pool {p.id}") for p in db.query(ContentPool).all()}
    latest_by_source: dict[int, ScrapeRun] = {}
    for run in list_scrape_runs(db, limit=80):
        sid = int(run.source_id or 0)
        if sid and sid not in latest_by_source:
            latest_by_source[sid] = run

    profiles_by_source: dict[int, ScrapeChannelProfile] = {}
    for prof in db.query(ScrapeChannelProfile).all():
        if prof.source_id:
            profiles_by_source[int(prof.source_id)] = prof

    active_runs = (
        db.query(ScrapeRun)
        .filter(ScrapeRun.status.in_(tuple(ACTIVE_RUN_STATUSES)))
        .order_by(ScrapeRun.id.asc())
        .all()
    )
    lock_holder = get_scrape_lock_holder()

    rows = []
    for src in sources:
        latest = latest_by_source.get(int(src.id))
        prof = profiles_by_source.get(int(src.id))
        phase = "idle"
        if not src.active:
            phase = "paused"
        elif latest and latest.status == "running":
            phase = "running"
        elif latest and latest.status == "queued":
            phase = "queued"
        elif latest and latest.status == "failed":
            phase = "error"
        elif latest and latest.status in ("skipped", "cancelled"):
            phase = "skipped"
        if latest and latest.status == "running" and latest.started_at:
            age = (utcnow() - latest.started_at).total_seconds()
            if age > 90 * 60:
                phase = "stalled"
        elif latest and latest.status == "queued" and latest.created_at:
            age = (utcnow() - latest.created_at).total_seconds()
            if age > 30 * 60:
                phase = "stalled"

        tg_url = public_telegram_url(
            username=prof.username if prof else None,
            identifier=src.identifier,
            invite_link=prof.invite_link if prof else None,
        )

        rows.append(
            {
                "source_id": int(src.id),
                "name": src.name,
                "identifier": src.identifier,
                "telegram_url": tg_url,
                "pool_id": int(src.pool_id or 0),
                "pool_name": pool_names.get(int(src.pool_id or 0), f"Pool {src.pool_id}"),
                "active": bool(src.active),
                "schedule_enabled": bool(src.schedule_enabled),
                "schedule_cron": src.schedule_cron,
                "media_types": normalize_media_types(src.media_types),
                "max_messages_per_run": int(src.max_messages_per_run or 50),
                "last_scraped_at": src.last_scraped_at.isoformat() if src.last_scraped_at else None,
                "phase": phase,
                "latest_run": scrape_run_to_dict(latest) if latest else None,
                "participants_count": prof.participants_count if prof else None,
                "avg_views_sample": prof.avg_views_sample if prof else None,
                "max_views_sample": prof.max_views_sample if prof else None,
                "views_sampled": prof.views_sampled if prof else 0,
                "posts_per_day": prof.posts_per_day if prof else None,
                "tags_sample": prof.tags_sample if prof else None,
                "suggested_pool_keys": prof.suggested_pool_keys if prof else None,
                "folder_label": prof.folder_label if prof else None,
            }
        )

    counts = {
        "total": len(rows),
        "running": sum(1 for r in rows if r["phase"] == "running"),
        "queued": sum(1 for r in rows if r["phase"] == "queued"),
        "stalled": sum(1 for r in rows if r["phase"] == "stalled"),
        "error": sum(1 for r in rows if r["phase"] == "error"),
        "paused": sum(1 for r in rows if r["phase"] == "paused"),
        "idle": sum(1 for r in rows if r["phase"] == "idle"),
        "autonomous": sum(1 for r in rows if r["active"] and r["schedule_enabled"]),
    }
    return {
        "lock_holder_run_id": lock_holder,
        "active_runs": [scrape_run_to_dict(r) for r in active_runs],
        "counts": counts,
        "sources": rows,
        "scrape_mode": "sequential",
        "scrape_mode_note": "One scrape at a time (shared scraper.session Redis lock). Parallel corpora need separate sessions.",
    }