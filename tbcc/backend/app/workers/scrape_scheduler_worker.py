from app.workers.celery_app import celery


@celery.task(name="app.workers.scrape_scheduler_worker.tick_scheduled_scrapes")
def tick_scheduled_scrapes():
    from app.services.scrape_run_service import tick_scheduled_scrapes as _tick

    return _tick()
