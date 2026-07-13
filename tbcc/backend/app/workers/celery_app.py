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
    "app.workers.vip_welcome_worker",
    "app.workers.milestone_worker",
    "app.workers.landing_bulletin_worker",
    "app.workers.media_auto_tag_worker",
    "app.workers.link_resolver_worker",
    "app.workers.listening_relay_worker",
    "app.workers.loot_promo_worker",
    "app.workers.import_telegram_worker",
    "app.workers.myjd_worker",
    "app.workers.mega_scraper_worker",
    "app.workers.buffer_armory_worker",
    "app.workers.network_liveness_worker",
    "app.workers.content_performance_worker",
    "app.workers.drop_countdown_worker",
    "app.workers.topic_mirror_worker",
    "app.workers.storage_pool_seed_worker",
    "app.workers.vip_weekly_mega_worker",
    "app.workers.thumbnail_warm_worker",
    "app.workers.k2s_mirror_worker",
    "app.workers.income_poll_worker",
    "app.workers.erome_analytics_worker",
    "app.workers.market_intel_worker",
    "app.workers.emoji_factory_worker",
    "app.workers.export_flywheel_worker",
    "app.workers.buffer_metrics_worker",
    "app.workers.sent_cache_composer_worker",
    "app.workers.sale_announce_worker",
]

celery.conf.task_routes = {
    "app.workers.scraper_worker.*": {"queue": "scrape"},
    "app.workers.mega_scraper_worker.*": {"queue": "scrape"},
    "app.workers.scrape_scheduler_worker.*": {"queue": "scrape"},
    "app.workers.scheduler_worker.*": {"queue": "celery"},
    # Scheduler lane (Beat due rows + manual Post now) — isolated from pool auto-post.
    "app.workers.poster_worker.post_scheduled_text": {"queue": "post_scheduler"},
    "app.workers.poster_worker.drain_scheduled_post_queue": {"queue": "post_scheduler"},
    "app.workers.poster_worker.*": {"queue": "post"},
    "app.workers.subscription_worker.*": {"queue": "subscription"},
    "app.workers.grant_access_worker.*": {"queue": "subscription"},
    "app.workers.milestone_worker.*": {"queue": "subscription"},
    "app.workers.landing_bulletin_worker.*": {"queue": "subscription"},
    # Ops lanes (Phase 4): heavy, non-latency-critical Beat ticks route off the home `celery`
    # worker so run_schedule (post_scheduler lane) never serializes behind them on the solo pool.
    # Consumed by TBCC-Celery-Ops (-Q ops_growth,ops_relay,ops_erome). If that worker is not
    # running, add these queues to TBCC_CELERY_HOME_QUEUES or the tasks strand in Redis.
    "app.workers.listening_relay_worker.*": {"queue": "ops_relay"},
    "app.workers.export_flywheel_worker.*": {"queue": "ops_growth"},
    "app.workers.income_poll_worker.*": {"queue": "ops_growth"},
    "app.workers.market_intel_worker.*": {"queue": "ops_growth"},
    "app.workers.storage_pool_seed_worker.*": {"queue": "ops_growth"},
    "app.workers.erome_analytics_worker.*": {"queue": "ops_erome"},
    # Light / user-facing tasks stay on the home worker.
    "app.workers.loot_promo_worker.*": {"queue": "celery"},
    "app.workers.sale_announce_worker.*": {"queue": "celery"},
    "app.workers.import_telegram_worker.*": {"queue": "telegram"},
    "app.workers.sent_cache_composer_worker.*": {"queue": "telegram"},
    "app.workers.media_auto_tag_worker.*": {"queue": "celery"},
    "app.workers.link_resolver_worker.*": {"queue": "celery"},
    "app.workers.myjd_worker.*": {"queue": "celery"},
    "app.workers.network_liveness_worker.*": {"queue": "subscription"},
    "app.workers.drop_countdown_worker.*": {"queue": "subscription"},
    "app.workers.topic_mirror_worker.*": {"queue": "telegram"},
    "app.workers.thumbnail_warm_worker.*": {"queue": "telegram"},
    "app.workers.k2s_mirror_worker.*": {"queue": "celery"},
    "app.workers.content_performance_worker.*": {"queue": "celery"},
    "app.workers.emoji_factory_worker.*": {"queue": "celery"},
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
    "buffer-armory-refill": {
        "task": "app.workers.buffer_armory_worker.refill_buffer_armory",
        "schedule": crontab(minute=15, hour="*/6"),
    },
}


def _liveness_fomo_crontab_hours() -> str:
    raw = (os.getenv("TBCC_LIVENESS_MILESTONE_FOMO_HOURS") or "6").strip()
    try:
        n = max(1, min(24, int(raw)))
    except ValueError:
        n = 6
    return f"*/{n}"


def _view_refresh_crontab_minutes() -> str:
    raw = (os.getenv("TBCC_VIEW_REFRESH_BEAT_MINUTES") or "30").strip()
    try:
        n = max(5, min(59, int(raw)))
    except ValueError:
        n = 30
    return f"*/{n}"


celery.conf.beat_schedule["refresh-post-views"] = {
    "task": "app.workers.content_performance_worker.refresh_post_views",
    "schedule": crontab(minute=_view_refresh_crontab_minutes()),
}

celery.conf.beat_schedule["aof-milestone-fomo"] = {
    "task": "app.workers.network_liveness_worker.post_milestone_fomo",
    "schedule": crontab(minute=20, hour=_liveness_fomo_crontab_hours()),
}

celery.conf.beat_schedule["vip-weekly-mega"] = {
    "task": "app.workers.vip_weekly_mega_worker.run_weekly_vip_mega",
    "schedule": crontab(minute=5, hour="*"),
}


def _storage_pool_seed_crontab_hours() -> str:
    raw = (os.getenv("TBCC_STORAGE_POOL_SEED_HOURS") or "4").strip()
    try:
        n = max(1, min(24, int(raw)))
    except ValueError:
        n = 4
    return f"*/{n}"


celery.conf.beat_schedule["storage-pool-seed"] = {
    "task": "app.workers.storage_pool_seed_worker.seed_pools_from_storage_hub",
    "schedule": crontab(minute=40, hour=_storage_pool_seed_crontab_hours()),
}


# Phase 1: internal thin-lane backfill (replaces public drop-signal posts). Opt-in; routes to
# ops_growth (Phase 4). Shares the global Telegram account lock with posting — keep to ~4h.
if (os.getenv("TBCC_THIN_POOL_BACKFILL_ENABLED") or "0").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
):
    celery.conf.beat_schedule["thin-pool-backfill"] = {
        "task": "app.workers.storage_pool_seed_worker.backfill_thin_pools",
        "schedule": crontab(minute=55, hour="*/4"),
    }


def _income_poll_crontab_hours() -> str:
    raw = (os.getenv("TBCC_INCOME_POLL_HOURS") or "6").strip()
    try:
        n = max(1, min(168, int(raw)))
    except ValueError:
        n = 6
    return f"*/{n}"


if (os.getenv("TBCC_INCOME_POLL_ENABLED") or "1").strip().lower() not in (
    "0",
    "false",
    "no",
    "off",
):
    celery.conf.beat_schedule["income-poll"] = {
        "task": "app.workers.income_poll_worker.poll_income_sources",
        "schedule": crontab(minute=25, hour=_income_poll_crontab_hours()),
    }


def _erome_view_sync_crontab_hours() -> str:
    raw = (os.getenv("TBCC_EROME_VIEW_SYNC_HOURS") or "6").strip()
    try:
        n = max(1, min(24, int(raw)))
    except ValueError:
        n = 6
    return f"*/{n}"


if (os.getenv("TBCC_EROME_VIEW_SYNC_ENABLED") or "1").strip().lower() not in (
    "0",
    "false",
    "no",
    "off",
):
    celery.conf.beat_schedule["erome-view-sync"] = {
        "task": "app.workers.erome_analytics_worker.sync_erome_views",
        "schedule": crontab(minute=10, hour=_erome_view_sync_crontab_hours()),
    }

if (os.getenv("TBCC_MARKET_INTEL_PROBE_ENABLED") or "1").strip().lower() not in (
    "0",
    "false",
    "no",
    "off",
):
    celery.conf.beat_schedule["market-intel-probe"] = {
        "task": "app.workers.market_intel_worker.run_market_intel_probe",
        "schedule": crontab(minute=20, hour="*/6"),
    }

if (os.getenv("TBCC_MARKET_INTEL_CYCLE_ENABLED") or "1").strip().lower() not in (
    "0",
    "false",
    "no",
    "off",
):
    _cycle_minute = int((os.getenv("TBCC_MARKET_INTEL_CYCLE_MINUTE") or "5").strip() or "5")
    _cycle_hour = int((os.getenv("TBCC_MARKET_INTEL_CYCLE_HOUR") or "9").strip() or "9")
    _cycle_dow = int((os.getenv("TBCC_MARKET_INTEL_CYCLE_WEEKDAY") or "1").strip() or "1")
    celery.conf.beat_schedule["market-intel-weekly-cycle"] = {
        "task": "app.workers.market_intel_worker.run_weekly_market_intel_cycle",
        "schedule": crontab(minute=_cycle_minute, hour=_cycle_hour, day_of_week=_cycle_dow),
    }


def _export_flywheel_crontab_minutes() -> str:
    raw = (os.getenv("TBCC_EXPORT_FLYWHEEL_TICK_MINUTES") or "15").strip()
    try:
        n = max(5, min(120, int(raw)))
    except ValueError:
        n = 15
    return f"*/{n}"


if (os.getenv("TBCC_EXPORT_FLYWHEEL_ENABLED") or "1").strip().lower() not in (
    "0",
    "false",
    "no",
    "off",
):
    celery.conf.beat_schedule["export-flywheel-tick"] = {
        "task": "app.workers.export_flywheel_worker.export_flywheel_tick",
        "schedule": crontab(minute=_export_flywheel_crontab_minutes()),
    }


if (os.getenv("TBCC_BUFFER_METRICS_SYNC_ENABLED") or "1").strip().lower() not in (
    "0",
    "false",
    "no",
    "off",
):
    celery.conf.beat_schedule["buffer-metrics-sync"] = {
        "task": "app.workers.buffer_metrics_worker.sync_buffer_metrics",
        "schedule": crontab(minute=45, hour="*/2"),
    }
