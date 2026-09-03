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
        # Process/compose env wins over file (island Beat gates + secrets injection).
        load_dotenv(_p, override=False)
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
    "app.workers.scrape_micro_pull_worker",
    "app.workers.gatekeeper_review_worker",
    "app.workers.scheduler_worker",
    "app.workers.subscription_worker",
    "app.workers.grant_access_worker",
    "app.workers.vip_welcome_worker",
    "app.workers.milestone_worker",
    "app.workers.landing_bulletin_worker",
    "app.workers.media_auto_tag_worker",
    "app.workers.link_resolver_worker",
    "app.workers.listening_relay_worker",
    "app.workers.goblin_worker",
    "app.workers.loot_promo_worker",
    "app.workers.loot_creator_recruitment_worker",
    "app.workers.mainhub_channel_spotlight_worker",
    "app.workers.import_telegram_worker",
    "app.workers.myjd_worker",
    "app.workers.mega_scraper_worker",
    "app.workers.buffer_armory_worker",
    "app.workers.stars_bait_outreach_worker",
    "app.workers.lifecycle_dm_worker",
    "app.workers.content_performance_worker",
    "app.workers.drop_countdown_worker",
    "app.workers.topic_mirror_worker",
    "app.workers.storage_pool_seed_worker",
    "app.workers.lane_survivor_refill_worker",
    "app.workers.sent_vault_lane_refill_worker",
    "app.workers.tag_backfill_worker",
    "app.workers.traffic_pulse_worker",
    "app.workers.inbox_intake_worker",
    "app.workers.storage_auto_pipe_worker",
    "app.workers.vip_weekly_mega_worker",
    "app.workers.weekly_build_log_worker",
    "app.workers.revenue_brief_worker",
    "app.workers.thumbnail_warm_worker",
    "app.workers.storage_hub_r2_export_worker",
    "app.workers.network_liveness_worker",
    "app.workers.k2s_mirror_worker",
    "app.workers.income_poll_worker",
    "app.workers.erome_analytics_worker",
    "app.workers.market_intel_worker",
    "app.workers.emoji_factory_worker",
    "app.workers.export_flywheel_worker",
    "app.workers.buffer_metrics_worker",
    "app.workers.sent_cache_composer_worker",
    "app.workers.topic_rebundle_worker",
    "app.workers.sale_announce_worker",
    "app.workers.loot_reveal_video_worker",
    "app.workers.creative_generate_worker",
]

celery.conf.task_routes = {
    "app.workers.scraper_worker.*": {"queue": "scrape"},
    "app.workers.mega_scraper_worker.*": {"queue": "scrape"},
    "app.workers.scrape_scheduler_worker.*": {"queue": "scrape"},
    # Hub forwarding (SCRP → Storage topic) uses import Telethon — must run on telegram lane
    # (revenue island worker consumes telegram; batch pool scrapes stay on GCP scrape queue).
    "app.workers.scrape_micro_pull_worker.*": {"queue": "telegram"},
    "app.workers.gatekeeper_review_worker.*": {"queue": "telegram"},
    "app.workers.inbox_intake_worker.*": {"queue": "telegram"},
    # Hub lane auto-pipe queues Telethon deposits — must land on telegram, not default celery.
    "app.workers.storage_auto_pipe_worker.*": {"queue": "telegram"},
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
    "app.workers.goblin_worker.*": {"queue": "ops_relay"},
    "app.workers.export_flywheel_worker.*": {"queue": "ops_growth"},
    "app.workers.income_poll_worker.*": {"queue": "ops_growth"},
    "app.workers.market_intel_worker.*": {"queue": "ops_growth"},
    # Telethon hub→pool deposits — island worker only consumes celery/subscription/telegram.
    # Keep on telegram (not ops_growth) or seeds strand forever on revenue island.
    "app.workers.storage_pool_seed_worker.*": {"queue": "telegram"},
    "app.workers.lane_survivor_refill_worker.*": {"queue": "telegram"},
    "app.workers.sent_vault_lane_refill_worker.*": {"queue": "telegram"},
    # NSFW/CLIP classify still hits the Telethon download path for non-local media.
    "app.workers.tag_backfill_worker.*": {"queue": "telegram"},
    "app.workers.erome_analytics_worker.*": {"queue": "ops_erome"},
    # Light / user-facing tasks stay on the home worker.
    "app.workers.loot_promo_worker.*": {"queue": "celery"},
    "app.workers.traffic_pulse_worker.*": {"queue": "celery"},
    "app.workers.sale_announce_worker.*": {"queue": "celery"},
    "app.workers.import_telegram_worker.*": {"queue": "telegram"},
    "app.workers.sent_cache_composer_worker.*": {"queue": "telegram"},
    "app.workers.topic_rebundle_worker.*": {"queue": "telegram"},
    # Enrich downloads the media over Telethon, so it belongs on the telegram
    # worker that already owns admin.session. On the general celery queue it let
    # a second pool of processes open that sqlite session concurrently, which
    # showed up as "database is locked" storms and auto-applied telegram_relief.
    "app.workers.media_auto_tag_worker.auto_tag_media_enrich": {"queue": "telegram"},
    "app.workers.media_auto_tag_worker.*": {"queue": "celery"},
    "app.workers.link_resolver_worker.*": {"queue": "celery"},
    "app.workers.myjd_worker.*": {"queue": "celery"},
    "app.workers.network_liveness_worker.*": {"queue": "subscription"},
    "app.workers.weekly_build_log_worker.*": {"queue": "subscription"},
    "app.workers.drop_countdown_worker.*": {"queue": "subscription"},
    "app.workers.topic_mirror_worker.*": {"queue": "telegram"},
    "app.workers.thumbnail_warm_worker.*": {"queue": "telegram"},
    "app.workers.storage_hub_r2_export_worker.*": {"queue": "telegram"},
    "app.workers.k2s_mirror_worker.*": {"queue": "celery"},
    "app.workers.content_performance_worker.*": {"queue": "celery"},
    "app.workers.emoji_factory_worker.*": {"queue": "celery"},
}

# AOF landing bulletin: task runs every hour UTC; task checks dashboard/env hour (no beat restart needed).
# Windows: avoid prefork + Telethon asyncio teardown issues; use solo pool (one process).
if os.name == "nt":
    celery.conf.worker_pool = "solo"
    celery.conf.worker_concurrency = 1


def _env_flag(name: str, default: str = "0") -> bool:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        raw = default
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


def _revenue_island_active() -> bool:
    """True when this process is the dedicated revenue VPS (not home / GCP scrape)."""
    return _env_flag("TBCC_REVENUE_ISLAND_ACTIVE", "0")


def _beat_schedule_minutes() -> str:
    raw = (os.getenv("TBCC_BEAT_SCHEDULE_MINUTES") or "2").strip()
    try:
        n = max(1, min(59, int(raw)))
    except ValueError:
        n = 2
    return f"*/{n}"


def _buffer_armory_refill_crontab_hours() -> str:
    raw = (os.getenv("TBCC_BUFFER_ARMORY_REFILL_HOURS") or "2").strip()
    try:
        n = max(1, min(12, int(raw)))
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
    "loot-creator-recruitment-room": {
        "task": "app.workers.loot_creator_recruitment_worker.send_loot_room_creator_recruitment",
        "schedule": crontab(minute=5, hour="*"),
    },
    "loot-creator-recruitment-lane": {
        "task": "app.workers.loot_creator_recruitment_worker.send_random_lane_creator_recruitment",
        "schedule": crontab(minute=10, hour="*"),
    },
    "mainhub-channel-spotlight": {
        "task": "app.workers.mainhub_channel_spotlight_worker.send_mainhub_channel_spotlight",
        "schedule": crontab(minute=15, hour="*"),
    },
    "lane-of-day-liveness-refresh": {
        "task": "app.workers.mainhub_channel_spotlight_worker.refresh_lane_of_the_day_liveness",
        "schedule": crontab(minute=5, hour=0),
    },
    "listening-relay-lastfm": {
        "task": "app.workers.listening_relay_worker.poll_listening_relay_lastfm",
        "schedule": crontab(minute="*/2"),
    },
    "buffer-armory-refill": {
        "task": "app.workers.buffer_armory_worker.refill_buffer_armory",
        "schedule": crontab(minute=20, hour=_buffer_armory_refill_crontab_hours()),
    },
}

# Cron scrape ticks only when a scrape consumer exists (GCP micro). Revenue island
# has no scrape queue worker — default off so Redis does not fill with orphans.
_scrape_sched_default = "0" if _revenue_island_active() else "1"
if _env_flag("TBCC_SCRAPE_SCHEDULER_ENABLED", _scrape_sched_default):
    celery.conf.beat_schedule["scrape-scheduler-tick"] = {
        "task": "app.workers.scrape_scheduler_worker.tick_scheduled_scrapes",
        "schedule": crontab(minute="*/5"),
        "options": {"expires": 240},
    }

if (os.getenv("TBCC_CREATIVE_GEN_ENABLED") or "0").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
):
    celery.conf.beat_schedule["creative-generate-tick"] = {
        "task": "app.workers.creative_generate_worker.run_creative_generate_tick",
        "schedule": crontab(minute=35, hour="*/6"),
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

celery.conf.beat_schedule["weekly-build-log"] = {
    "task": "app.workers.weekly_build_log_worker.run_weekly_build_log",
    "schedule": crontab(minute=30, hour="*"),
}

celery.conf.beat_schedule["revenue-brief"] = {
    "task": "app.workers.revenue_brief_worker.run_revenue_brief",
    "schedule": crontab(minute=30, hour="*"),
}


def _storage_pool_seed_crontab_hours() -> str:
    raw = (os.getenv("TBCC_STORAGE_POOL_SEED_HOURS") or "4").strip()
    try:
        n = max(1, min(24, int(raw)))
    except ValueError:
        n = 4
    return f"*/{n}"


celery.conf.beat_schedule["intake-schedule-tick"] = {
    "task": "app.workers.inbox_intake_worker.run_intake_schedule_tick",
    "schedule": crontab(minute="*/5"),
}

# Backstop for deposits that never got a lane decision (focus pause, Telethon
# failure, worker restart). Without it a missed item is never retried.
celery.conf.beat_schedule["enrich-backlog-sweep"] = {
    "task": "app.workers.media_auto_tag_worker.auto_tag_enrich_backlog_tick",
    "schedule": crontab(minute="*/10"),
}

# Legacy alias — storage-pool-seed now delegates to intake tick (force all due lanes).
celery.conf.beat_schedule["storage-pool-seed"] = {
    "task": "app.workers.inbox_intake_worker.run_intake_schedule_tick",
    "schedule": crontab(minute=40, hour=_storage_pool_seed_crontab_hours()),
    "kwargs": {"force": False},
}

if (os.getenv("TBCC_SCRAPE_MICRO_PULL_ENABLED") or "0").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
):
    celery.conf.beat_schedule["scrape-micro-pull"] = {
        "task": "app.workers.scrape_micro_pull_worker.run_micro_pull_tick",
        "schedule": crontab(minute=15, hour="*/2"),
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

# Recycle posted/survivor stock into approved rotation (monthly deep backfill; dry spells
# use on-demand SENT VAULT pickup at send time — see sent_vault_lane_refill).
if (os.getenv("TBCC_LANE_SURVIVOR_REFILL_ENABLED") or "0").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
):
    celery.conf.beat_schedule["lane-survivor-refill"] = {
        "task": "app.workers.lane_survivor_refill_worker.refill_lanes_from_survivors",
        "schedule": crontab(minute=20, hour=7, day_of_month="1,15"),
    }

# Dry lanes → SENT VAULT recycle (Beat backfill every 6h; send-time dry spell is on-demand).
if (os.getenv("TBCC_SENT_VAULT_LANE_REFILL_ENABLED") or "1").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
):
    celery.conf.beat_schedule["sent-vault-lane-refill"] = {
        "task": "app.workers.sent_vault_lane_refill_worker.refill_dry_lanes_from_sent_vault",
        "schedule": crontab(minute=15, hour="*/6"),
    }

# Thin-tag trickle backfill — off by default; the bulk catch-up is the manual
# script (scripts/backfill_media_tags.py). Enable this only for an ongoing
# low-rate top-up once the initial backlog is cleared.
if (os.getenv("TBCC_TAG_BACKFILL_SWEEP_ENABLED") or "0").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
):
    celery.conf.beat_schedule["tag-backfill-sweep"] = {
        "task": "app.workers.tag_backfill_worker.tag_backfill_sweep_tick",
        "schedule": crontab(minute=45, hour="*/2"),
    }


def _traffic_pulse_digest_crontab_minutes() -> str:
    from app.services.traffic_pulse import traffic_pulse_digest_minutes

    n = traffic_pulse_digest_minutes()
    return f"*/{n}"


if (os.getenv("TBCC_TRAFFIC_PULSE_ENABLED") or "1").strip().lower() not in (
    "0",
    "false",
    "no",
    "off",
):
    celery.conf.beat_schedule["traffic-pulse-digest"] = {
        "task": "app.workers.traffic_pulse_worker.send_traffic_pulse_digest",
        "schedule": crontab(minute=_traffic_pulse_digest_crontab_minutes()),
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

# Reddit hot.json is often 403 from VPS IPs — default off on revenue island.
_mi_probe_default = "0" if _revenue_island_active() else "1"
if _env_flag("TBCC_MARKET_INTEL_PROBE_ENABLED", _mi_probe_default):
    celery.conf.beat_schedule["market-intel-probe"] = {
        "task": "app.workers.market_intel_worker.run_market_intel_probe",
        "schedule": crontab(minute=20, hour="*/6"),
    }

_mi_cycle_default = "0" if _revenue_island_active() else "1"
if _env_flag("TBCC_MARKET_INTEL_CYCLE_ENABLED", _mi_cycle_default):
    _cycle_minute = int((os.getenv("TBCC_MARKET_INTEL_CYCLE_MINUTE") or "5").strip() or "5")
    _cycle_hour = int((os.getenv("TBCC_MARKET_INTEL_CYCLE_HOUR") or "9").strip() or "9")
    _cycle_dow = int((os.getenv("TBCC_MARKET_INTEL_CYCLE_WEEKDAY") or "1").strip() or "1")
    celery.conf.beat_schedule["market-intel-weekly-cycle"] = {
        "task": "app.workers.market_intel_worker.run_weekly_market_intel_cycle",
        "schedule": crontab(minute=_cycle_minute, hour=_cycle_hour, day_of_week=_cycle_dow),
    }


def _storage_hub_r2_export_crontab_minutes() -> str:
    raw = (os.getenv("TBCC_STORAGE_HUB_R2_EXPORT_MINUTES") or "10").strip()
    try:
        n = max(5, min(59, int(raw)))
    except ValueError:
        n = 10
    return f"*/{n}"


# Volume path: Hub → R2. Default on for revenue island; opt-in elsewhere.
_r2_export_default = "1" if _revenue_island_active() else "0"
if _env_flag("TBCC_STORAGE_HUB_R2_EXPORT_ENABLED", _r2_export_default):
    _r2_limit = 15
    try:
        _r2_limit = max(1, min(50, int((os.getenv("TBCC_STORAGE_HUB_R2_EXPORT_LIMIT") or "15").strip())))
    except ValueError:
        _r2_limit = 15
    celery.conf.beat_schedule["storage-hub-r2-export"] = {
        "task": "app.workers.storage_hub_r2_export_worker.export_storage_hub_media_to_r2",
        "schedule": crontab(minute=_storage_hub_r2_export_crontab_minutes()),
        "kwargs": {"since_id": 0, "limit": _r2_limit, "only_missing_r2": True},
        "options": {"expires": 540},
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


def _buffer_metrics_sync_crontab_hours() -> str:
    raw = (os.getenv("TBCC_BUFFER_METRICS_SYNC_HOURS") or "2").strip()
    try:
        n = max(2, min(24, int(raw)))
    except ValueError:
        n = 2
    return f"*/{n}"


if (os.getenv("TBCC_BUFFER_METRICS_SYNC_ENABLED") or "1").strip().lower() not in (
    "0",
    "false",
    "no",
    "off",
):
    celery.conf.beat_schedule["buffer-metrics-sync"] = {
        "task": "app.workers.buffer_metrics_worker.sync_buffer_metrics",
        "schedule": crontab(minute=45, hour=_buffer_metrics_sync_crontab_hours()),
    }


def _lifecycle_dm_crontab_hour() -> int:
    raw = (os.getenv("TBCC_LIFECYCLE_DM_HOUR_UTC") or "14").strip()
    try:
        return max(0, min(23, int(raw)))
    except ValueError:
        return 14


if (os.getenv("TBCC_LIFECYCLE_DM_ENABLED") or "").strip().lower() in ("1", "true", "yes", "on"):
    celery.conf.beat_schedule["lifecycle-dm-tick"] = {
        "task": "app.workers.lifecycle_dm_worker.run_lifecycle_dm_tick",
        "schedule": crontab(minute=20, hour=_lifecycle_dm_crontab_hour()),
    }

if (os.getenv("TBCC_STARS_BAIT_DM_ENABLED") or "").strip().lower() in ("1", "true", "yes", "on"):
    _sb_min = (os.getenv("TBCC_STARS_BAIT_DM_INTERVAL_MIN") or "45").strip()
    try:
        _sb_n = max(15, min(1440, int(_sb_min)))
    except ValueError:
        _sb_n = 45
    if _sb_n >= 60:
        _sb_hours = max(1, min(24, _sb_n // 60))
        celery.conf.beat_schedule["stars-bait-dm-pace"] = {
            "task": "app.workers.stars_bait_outreach_worker.run_stars_bait_dm_pace_tick",
            "schedule": crontab(minute=10, hour=f"*/{_sb_hours}"),
        }
    else:
        celery.conf.beat_schedule["stars-bait-dm-pace"] = {
            "task": "app.workers.stars_bait_outreach_worker.run_stars_bait_dm_pace_tick",
            "schedule": crontab(minute=f"*/{_sb_n}"),
        }
