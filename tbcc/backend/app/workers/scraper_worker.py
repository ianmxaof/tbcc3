import asyncio
import os

from app.workers.celery_app import celery


@celery.task(name="app.workers.scraper_worker.run_scrape", bind=True)
def run_scrape(self, source_id: int, trigger: str = "manual", run_id: int | None = None):
    from app.database.session import SessionLocal
    from app.models.scrape_run import ScrapeRun
    from app.models.source import Source
    from app.services.scrape_run_service import (
        acquire_scrape_lock,
        create_scrape_run,
        finish_run_from_stats,
        mark_run_running,
        mark_run_skipped,
        release_scrape_lock,
        utcnow,
    )
    from bots.scraper_bot import run_scraper

    db = SessionLocal()
    locked_run_id = None
    try:
        source = db.query(Source).filter(Source.id == source_id).first()
        if not source:
            return {"ok": False, "error": "source_not_found"}
        if run_id is not None:
            run = db.query(ScrapeRun).filter(ScrapeRun.id == run_id).first()
            if not run:
                run = create_scrape_run(
                    db,
                    source,
                    trigger=trigger or "manual",
                    celery_task_id=getattr(self.request, "id", None),
                )
        else:
            run = create_scrape_run(
                db,
                source,
                trigger=trigger or "manual",
                celery_task_id=getattr(self.request, "id", None),
            )
        locked_run_id = run.id
        if not source.active:
            mark_run_skipped(db, run, "source_inactive")
            return {"ok": False, "run_id": run.id, "status": "skipped"}
        ident_raw = (source.identifier or "").strip()
        try:
            chat_id = int(ident_raw)
            from app.models.scrape_channel_profile import ScrapeChannelProfile

            prof = (
                db.query(ScrapeChannelProfile)
                .filter(ScrapeChannelProfile.chat_id == chat_id)
                .first()
            )
            if prof and prof.forward_enabled is False:
                mark_run_skipped(db, run, "forward_restricted", prof.skip_reason)
                return {"ok": False, "run_id": run.id, "status": "skipped"}
        except (TypeError, ValueError):
            pass
        if (source.source_type or "").strip().lower() != "telegram_channel":
            mark_run_skipped(db, run, "source_inactive", "Only telegram_channel sources can be scraped.")
            return {"ok": False, "run_id": run.id, "status": "skipped"}
        if not acquire_scrape_lock(run.id):
            mark_run_skipped(db, run, "lock_busy")
            return {"ok": False, "run_id": run.id, "status": "skipped"}
        from app.services.scrape_run_service import is_scrape_cancel_requested, mark_run_cancelled, clear_scrape_cancel

        if is_scrape_cancel_requested(run.id):
            mark_run_cancelled(db, run, "user_cancelled")
            clear_scrape_cancel(run.id)
            release_scrape_lock(run.id)
            locked_run_id = None
            return {"ok": False, "run_id": run.id, "status": "cancelled"}
        mark_run_running(db, run)
        try:
            if is_scrape_cancel_requested(run.id):
                mark_run_cancelled(db, run, "user_cancelled")
                clear_scrape_cancel(run.id)
                return {"ok": False, "run_id": run.id, "status": "cancelled"}
            stats = asyncio.run(
                run_scraper(
                    api_id=os.environ["API_ID"],
                    api_hash=os.environ["API_HASH"],
                    source_id=source_id,
                )
            )
            finish_run_from_stats(db, run, stats)
            if int(stats.get("stored") or 0) > 0 and run.status == "done":
                source.last_scraped_at = utcnow()
                db.commit()
            return {"ok": True, "run_id": run.id, "status": run.status, "stored": stats.get("stored", 0)}
        finally:
            release_scrape_lock(run.id)
            locked_run_id = None
            clear_scrape_cancel(run.id)
    except Exception as e:
        if locked_run_id is not None:
            try:
                from app.services.scrape_run_service import ERROR_CATALOG

                run = db.query(ScrapeRun).filter(ScrapeRun.id == locked_run_id).first()
                if run:
                    cat = ERROR_CATALOG["scraper_session"]
                    finish_run_from_stats(
                        db,
                        run,
                        {
                            "fatal": True,
                            "errors_count": 1,
                            "errors": [
                                {
                                    "code": "worker_exception",
                                    "message": cat["message"],
                                    "fix": cat["fix"],
                                    "detail": str(e)[:400],
                                }
                            ],
                        },
                    )
            except Exception:
                pass
            release_scrape_lock(locked_run_id)
        raise
    finally:
        db.close()
