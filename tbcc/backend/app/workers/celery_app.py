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
    "app.workers.scrape_scheduler_worker",
    "app.workers.scheduler_worker",
    "app.workers.subscription_worker",
    "app.workers.grant_access_worker",
    "app.workers.milestone_worker",
    "app.workers.landing_bulletin_worker",
    "app.workers.media_auto_tag_worker",
    "app.workers.link_resolver_worker",
    "app.workers.listening_relay_worker",
    "app.workers.loot_promo_worker",
    "app.workers.import_telegram_worker",
    "app.workers.myjd_worker",
]

celery.conf.task_routes = {
    "app.workers.scraper_worker.*": {"queue": "scrape"},
    "app.workers.scrape_scheduler_worker.*": {"queue": "scrape"},
    "app.workers.scheduler_worker.*": {"queue": "post"},
    "app.workers.poster_worker.*": {"queue": "post"},
    "app.workers.subscription_worker.*": {"queue": "subscription"},
    "app.workers.grant_access_worker.*": {"queue": "subscription"},
    "app.workers.milestone_worker.*": {"queue": "subscription"},
    "app.workers.landing_bulletin_worker.*": {"queue": "subscription"},
    # Last.fm relay polls on the general worker so TBCC-Celery-Post stays reserved for channel posts.
    "app.workers.listening_relay_worker.*": {"queue": "celery"},
    "app.workers.loot_promo_worker.*": {"queue": "celery"},
    "app.workers.import_telegram_worker.*": {"queue": "telegram"},
    "app.workers.media_auto_tag_worker.*": {"queue": "celery"},
    "app.workers.link_resolver_worker.*": {"queue": "celery"},
    "app.workers.myjd_worker.*": {"queue": "celery"},
}

# AOF landing bulletin: task runs every hour UTC; task checks dashboard/env hour (no beat restart needed).
# Windows: avoid prefork + Telethon asyncio teardown issues; use solo pool (one process).
if os.name == "nt":
    celery.conf.worker_pool = "solo"
    celery.conf.worker_concurrency = 1


def _beat_schedule_minutes() -> str:
    raw = (os.getenv("TBCC_BEAT_SCHEDULE_MINUTES") or "2").strip()
    try:
        n = max(1, min(59, int(raw)))
    except ValueError:
        n = 2
    return f"*/{n}"


celery.conf.beat_schedule = {
    "schedule-posts": {
        "task": "app.workers.scheduler_worker.run_schedule",
        "schedule": crontab(minute=_beat_schedule_minutes()),
    },
    "cleanup-expired-subscriptions": {
        "task": "app.workers.subscription_worker.cleanup_expired_subscriptions",
        "schedule": crontab(minute=0, hour=0),  # Daily at midnight UTC
    },
    "aof-landing-bulletin": {
        "task": "app.workers.landing_bulletin_worker.send_aof_landing_bulletin",
        "schedule": crontab(minute=0, hour="*"),
    },
    "loot-daily-promo": {
        "task": "app.workers.loot_promo_worker.send_loot_daily_promo",
        "schedule": crontab(minute=0, hour="*"),
    },
    "listening-relay-lastfm": {
        "task": "app.workers.listening_relay_worker.poll_listening_relay_lastfm",
        "schedule": crontab(minute="*/2"),
    },
    "scrape-scheduler-tick": {
        "task": "app.workers.scrape_scheduler_worker.tick_scheduled_scrapes",
        "schedule": crontab(minute="*/5"),
    },
}
