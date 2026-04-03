from app.workers.celery_app import celery
from app.database.session import SessionLocal
from app.services.post_scheduler import check_and_schedule


@celery.task(name="app.workers.scheduler_worker.run_schedule")
def run_schedule():
    db = SessionLocal()
    try:
        check_and_schedule(db)
    finally:
        db.close()
