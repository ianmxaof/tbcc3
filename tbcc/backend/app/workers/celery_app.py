from pathlib import Path

from dotenv import load_dotenv

# Load .env so API_ID/API_HASH etc. are available to workers (Celery runs in a separate process)
_load_paths = [
    Path(__file__).resolve().parent.parent.parent.parent / ".env",  # tbcc/.env
    Path(__file__).resolve().parent.parent.parent / ".env",         # backend/.env
    Path.cwd().parent / ".env",
    Path.cwd() / ".env",
]
for _p in _load_paths:
    if _p.exists():
        load_dotenv(_p, override=True)
        break

from celery import Celery
from celery.schedules import crontab
import os

celery = Celery(
    "tbcc",
    broker=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
    backend=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
)

celery.conf.include = [
    "app.workers.poster_worker",
    "app.workers.scraper_worker",
    "app.workers.scheduler_worker",
    "app.workers.subscription_worker",
    "app.workers.grant_access_worker",
    "app.workers.milestone_worker",
    "app.workers.landing_bulletin_worker",
    "app.workers.media_auto_tag_worker",
]

celery.conf.task_routes = {
    "app.workers.scraper_worker.*": {"queue": "scrape"},
    "app.workers.poster_worker.*": {"queue": "post"},
    "app.workers.subscription_worker.*": {"queue": "subscription"},
    "app.workers.grant_access_worker.*": {"queue": "subscription"},
    "app.workers.milestone_worker.*": {"queue": "subscription"},
    "app.workers.landing_bulletin_worker.*": {"queue": "subscription"},
}

# AOF landing bulletin: task runs every hour UTC; task checks dashboard/env hour (no beat restart needed).
celery.conf.beat_schedule = {
    "schedule-posts": {
        "task": "app.workers.scheduler_worker.run_schedule",
        "schedule": crontab(minute="*/5"),
    },
    "cleanup-expired-subscriptions": {
        "task": "app.workers.subscription_worker.cleanup_expired_subscriptions",
        "schedule": crontab(minute=0, hour=0),  # Daily at midnight UTC
    },
    "aof-landing-bulletin": {
        "task": "app.workers.landing_bulletin_worker.send_aof_landing_bulletin",
        "schedule": crontab(minute=0, hour="*"),
    },
}
