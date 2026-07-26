"""Phase 4 Celery queue routing: heavy ops ticks isolated from the post_scheduler lane.

Regression guard for the queue split — run_schedule must stay on the home `celery` queue
so it never serializes behind flywheel/relay/seed ticks on the solo worker.
"""

from app.workers.celery_app import celery


def _queue_for(task_name: str) -> str:
    route = celery.amqp.router.route({}, task_name) or {}
    q = route.get("queue")
    if q is None:
        return celery.conf.task_default_queue or "celery"
    return getattr(q, "name", q)


def test_ops_growth_tasks_route_off_home_queue():
    for task in (
        "app.workers.export_flywheel_worker.export_flywheel_tick",
        "app.workers.income_poll_worker.poll_income_sources",
        "app.workers.market_intel_worker.run_market_intel_probe",
        "app.workers.market_intel_worker.run_weekly_market_intel_cycle",
        "app.workers.storage_pool_seed_worker.seed_pools_from_storage_hub",
    ):
        assert _queue_for(task) == "ops_growth", task


def test_relay_and_erome_route_to_ops_lanes():
    assert (
        _queue_for("app.workers.listening_relay_worker.poll_listening_relay_lastfm")
        == "ops_relay"
    )
    assert (
        _queue_for("app.workers.listening_relay_worker.post_listening_relay_bot_api")
        == "ops_relay"
    )
    assert _queue_for("app.workers.erome_analytics_worker.sync_erome_views") == "ops_erome"


def test_scheduler_lane_unchanged():
    # The whole point of the split: the posting lanes are untouched.
    assert _queue_for("app.workers.scheduler_worker.run_schedule") == "celery"
    assert _queue_for("app.workers.poster_worker.post_scheduled_text") == "post_scheduler"
    assert _queue_for("app.workers.poster_worker.drain_scheduled_post_queue") == "post_scheduler"
    assert _queue_for("app.workers.poster_worker.post_pool") == "post"


def test_light_tasks_stay_on_home_queue():
    for task in (
        "app.workers.loot_promo_worker.send_loot_daily_promo",
        "app.workers.media_auto_tag_worker.auto_tag_media",
        "app.workers.link_resolver_worker.resolve_link",
        "app.workers.k2s_mirror_worker.mirror_to_k2s",
    ):
        assert _queue_for(task) == "celery", task
