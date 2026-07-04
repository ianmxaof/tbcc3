"""Celery: Telegram link scrape → mega pipeline → loot_modifiers."""

from __future__ import annotations

import asyncio
import logging
import os

from app.database.session import SessionLocal
from app.models.scrape_run import ScrapeRun
from app.services.mega_scrape_service import filter_channel_sources, run_mega_scrape
from app.services.scrape_run_service import (
    acquire_scrape_lock,
    finish_run_from_stats,
    mark_run_running,
    mark_run_skipped,
    release_scrape_lock,
    utcnow,
)
from app.workers.celery_app import celery

logger = logging.getLogger(__name__)


def _link_run_stats(result: dict) -> dict:
    st = result.get("stats") or {}
    return {
        "messages_scanned": int(st.get("messages_scanned") or 0),
        "stored": int(st.get("modifiers_created") or 0),
        "skipped_duplicate": int(st.get("skipped_duplicate") or 0),
        "skipped_media_type": int(st.get("skipped_obfuscated") or 0),
        "skipped_no_media": int(st.get("pipeline_failed") or 0),
        "errors_count": len(st.get("errors") or []),
        "errors": st.get("errors") or [],
        "fatal": not result.get("ok"),
        "error_summary": result.get("error") or (None if result.get("ok") else "link_scrape_failed"),
    }


def _finish_link_run(db, run: ScrapeRun, result: dict) -> None:
    stats = _link_run_stats(result)
    finish_run_from_stats(db, run, stats)
    if result.get("ok") and stats.get("stored", 0) > 0:
        run.error_summary = None
        run.status = "done"
        db.commit()


@celery.task(name="app.workers.mega_scraper_worker.run_mega_scrape_job", bind=True)
def run_mega_scrape_job(
    self,
    run_id: int,
    *,
    chat_ids: list[int] | None = None,
    kinds: list[str] | None = None,
    message_limit: int = 40,
    include_obfuscated: bool = False,
    execute: bool = True,
) -> dict:
    db = SessionLocal()
    locked = False
    try:
        run = db.query(ScrapeRun).filter(ScrapeRun.id == run_id).first()
        if not run:
            return {"ok": False, "error": "run_not_found"}
        if run.source_id != 0:
            mark_run_skipped(db, run, "source_inactive", "Not a link scrape run.")
            return {"ok": False, "run_id": run_id}

        if not acquire_scrape_lock(run_id):
            mark_run_skipped(db, run, "lock_busy")
            return {"ok": False, "run_id": run_id, "status": "skipped"}

        locked = True
        mark_run_running(db, run)
        run.celery_task_id = getattr(self.request, "id", None)
        db.commit()

        kind_set = set(kinds) if kinds else None
        result = asyncio.run(
            run_mega_scrape(
                os.environ["API_ID"],
                os.environ["API_HASH"],
                kinds=kind_set,
                chat_ids=chat_ids,
                messages_per_channel=message_limit,
                include_obfuscated=include_obfuscated,
                execute=execute,
            )
        )
        _finish_link_run(db, run, result)
        return {"ok": bool(result.get("ok")), "run_id": run_id, "result": result}
    except Exception as e:
        logger.exception("mega_scrape_job failed run_id=%s", run_id)
        try:
            run = db.query(ScrapeRun).filter(ScrapeRun.id == run_id).first()
            if run:
                finish_run_from_stats(
                    db,
                    run,
                    {
                        "fatal": True,
                        "error_summary": str(e)[:300],
                        "errors": [{"code": "internal_error", "message": str(e)[:300]}],
                        "errors_count": 1,
                    },
                )
        except Exception:
            pass
        return {"ok": False, "error": str(e)}
    finally:
        if locked:
            release_scrape_lock(run_id)
        db.close()


def create_link_scrape_run(
    db,
    *,
    label: str,
    chat_id: int | None = None,
    trigger: str = "manual",
) -> ScrapeRun:
    name = f"LINK: {label}" + (f" ({chat_id})" if chat_id else "")
    run = ScrapeRun(
        source_id=0,
        source_name=name[:256],
        pool_id=None,
        trigger=trigger,
        status="queued",
        created_at=utcnow(),
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run
