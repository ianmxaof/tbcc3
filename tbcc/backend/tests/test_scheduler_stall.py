"""Scheduler stall detection, pool priority, and queue purge helpers."""

import contextlib
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from app.services.post_scheduler import (
    check_and_schedule,
    count_overdue_scheduled_posts,
    post_queue_backlog_threshold,
    prioritize_scheduled_post_lane,
    scheduler_stall_minutes,
    _schedule_pool_interval_posts,
)
from app.services import system_health as sh


def test_post_queue_backlog_threshold_default():
    with patch.dict("os.environ", {}, clear=False):
        assert post_queue_backlog_threshold() == 5


def test_scheduler_stall_minutes_default():
    with patch.dict("os.environ", {}, clear=False):
        assert scheduler_stall_minutes() == 15


def test_count_overdue_scheduled_posts():
    db = MagicMock()
    post = MagicMock()
    post.id = 48
    post.name = "AOF BOP SCHEDULER"
    post.pool_id = 23
    post.channel_id = 16
    post.interval_minutes = 120
    post.last_posted_at = datetime.utcnow() - timedelta(minutes=130)
    post.posting_auto_paused_at = None
    db.query.return_value.filter.return_value.all.return_value = [post]
    overdue = count_overdue_scheduled_posts(db, min_overdue_minutes=5.0)
    assert len(overdue) == 1
    assert overdue[0]["id"] == 48
    assert overdue[0]["overdue_minutes"] >= 10.0


def test_prioritize_scheduled_post_lane_purges_pool_when_overdue():
    db = MagicMock()
    post = MagicMock()
    post.id = 48
    post.name = "AOF BOP SCHEDULER"
    post.pool_id = 23
    post.channel_id = 16
    post.interval_minutes = 120
    post.last_posted_at = datetime.utcnow() - timedelta(minutes=130)
    post.posting_auto_paused_at = None
    db.query.return_value.filter.return_value.all.return_value = [post]
    with patch("app.services.celery_queue_ops.purge_post_pool_tasks_from_queue") as purge:
        purge.return_value = {"ok": True, "removed": 2}
        out = prioritize_scheduled_post_lane(db)
    assert out["action"] == "purge_post_pool"
    assert out["overdue_count"] == 1
    purge.assert_called_once()


def test_schedule_pool_skips_blocked_pool_id():
    db = MagicMock()
    pool = MagicMock()
    pool.id = 23
    pool.auto_post_enabled = True
    pool.interval_minutes = 75
    pool.last_posted = datetime.utcnow() - timedelta(hours=2)
    pool.channel_id = 16
    pool_q = MagicMock()
    pool_q.all.return_value = [pool]
    db.query.return_value = pool_q
    now = datetime.utcnow()
    with patch("app.services.post_scheduler.pool_auto_post_enabled", return_value=True):
        with patch("app.services.post_scheduler._post_queue_length", return_value=0):
            with patch("app.services.post_scheduler.post_pool") as delay:
                _schedule_pool_interval_posts(db, now, blocked_pool_ids={23})
                delay.delay.assert_not_called()


def test_check_and_schedule_calls_priority_before_pool():
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = []
    with patch("app.services.post_scheduler.prioritize_scheduled_post_lane") as prio:
        with patch("app.services.post_scheduler._pool_ids_blocked_by_overdue_schedulers", return_value=set()):
            with patch("app.services.post_scheduler._schedule_pool_interval_posts") as pool:
                prio.return_value = {"ok": True, "overdue_count": 0}
                check_and_schedule(db)
                prio.assert_called_once_with(db)
                pool.assert_called_once()
    db.commit.assert_called_once()


# ---------------------------------------------------------------------------
# Scheduler watchdog (system_health.scheduler_watchdog_tick)
# ---------------------------------------------------------------------------


def _watchdog_env(
    *,
    overdue=0,
    post_len=0,
    focus="off",
    beat_paused=False,
    processing=0,
    cooldown_ok=True,
    enabled=True,
    sched=None,
):
    """Patch every external the tick reaches so only in-memory logic is exercised."""
    if sched is None:
        sched = {"beat_running": True, "celery_post_worker_running": True}
    stack = contextlib.ExitStack()
    p = stack.enter_context
    p(patch("app.services.system_health.collect_scheduling_health", return_value=sched))
    p(patch("app.services.system_health.health_auto_remediate_enabled", return_value=enabled))
    p(patch("app.services.system_health._auto_remediate_cooldown_ok", return_value=cooldown_ok))
    mark = p(patch("app.services.system_health._mark_auto_remediate_cooldown"))
    p(patch("app.services.post_scheduler.schedulers_stall_summary", return_value={"count": overdue}))
    p(patch("app.services.post_scheduler._post_queue_length", return_value=post_len))
    p(patch("app.services.post_scheduler.clear_post_scheduling_redis_state", return_value={}))
    p(patch("app.services.focus_profile.get_focus_state", return_value={"profile": focus}))
    p(patch("app.services.focus_profile.pause_beat_scheduling", return_value=beat_paused))
    p(patch("app.services.focus_profile.count_processing_import_jobs", return_value=processing))
    return stack, mark


def test_watchdog_resume_when_overdue_and_queue_nonempty():
    sh.reset_scheduler_watchdog_state()
    stack, mark = _watchdog_env(overdue=2, post_len=5)
    with stack:
        with patch(
            "app.services.post_scheduler.resume_scheduled_posting",
            return_value={"ok": True},
        ) as resume:
            out = sh.scheduler_watchdog_tick()
    resume.assert_called_once_with(purge_post_queue=True)
    mark.assert_any_call(["resume_scheduled_posting"])
    assert any(a["action"] == "resume_scheduled_posting" for a in out["actions"])
    assert sh._WATCHDOG_LAST_ACTION["action"] == "resume_scheduled_posting"


def test_watchdog_resume_on_deep_queue_even_without_overdue():
    sh.reset_scheduler_watchdog_state()
    # No scheduler overdue yet, but the post queue is backed up past the threshold (default 5).
    stack, mark = _watchdog_env(overdue=0, post_len=9)
    with stack:
        with patch(
            "app.services.post_scheduler.resume_scheduled_posting",
            return_value={"ok": True},
        ) as resume:
            out = sh.scheduler_watchdog_tick()
    resume.assert_called_once_with(purge_post_queue=True)
    mark.assert_any_call(["resume_scheduled_posting"])
    assert any(a["action"] == "resume_scheduled_posting" for a in out["actions"])


def test_watchdog_resume_when_overdue_and_empty_scheduler_queue():
    sh.reset_scheduler_watchdog_state()
    stack, mark = _watchdog_env(overdue=2, post_len=0)
    with stack:
        with patch(
            "app.services.post_scheduler.resume_scheduled_posting",
            return_value={"ok": True},
        ) as resume:
            out = sh.scheduler_watchdog_tick()
    resume.assert_called_once_with(purge_post_queue=True)
    mark.assert_any_call(["resume_scheduled_posting"])
    assert any(a["action"] == "resume_scheduled_posting" for a in out["actions"])


def test_watchdog_import_burst_restores_only_after_dwell():
    sh.reset_scheduler_watchdog_state()
    # First tick establishes the idle window; too soon to restore.
    stack1, _ = _watchdog_env(focus="import_burst", beat_paused=True, processing=0)
    with stack1:
        with patch("app.services.focus_profile.restore_focus_profile") as restore:
            sh.scheduler_watchdog_tick()
    restore.assert_not_called()
    assert sh._WATCHDOG_IMPORT_IDLE_SINCE is not None
    # Backdate the idle window past the dwell threshold, then tick again.
    sh._WATCHDOG_IMPORT_IDLE_SINCE = datetime.utcnow() - timedelta(minutes=10)
    stack2, _ = _watchdog_env(focus="import_burst", beat_paused=True, processing=0)
    with stack2:
        with patch(
            "app.services.focus_profile.restore_focus_profile",
            return_value={"ok": True},
        ) as restore:
            out = sh.scheduler_watchdog_tick()
    restore.assert_called_once()
    assert any(a["action"] == "restore_focus" for a in out["actions"])


def test_watchdog_import_burst_no_restore_while_processing():
    sh.reset_scheduler_watchdog_state()
    stack, _ = _watchdog_env(focus="import_burst", beat_paused=True, processing=2)
    with stack:
        with patch("app.services.focus_profile.restore_focus_profile") as restore:
            sh.scheduler_watchdog_tick()
    restore.assert_not_called()
    assert sh._WATCHDOG_IMPORT_IDLE_SINCE is None


def test_watchdog_actions_gated_when_remediate_disabled():
    sh.reset_scheduler_watchdog_state()
    stack, _ = _watchdog_env(overdue=5, post_len=9, enabled=False)
    with stack:
        with patch("app.services.post_scheduler.resume_scheduled_posting") as resume:
            out = sh.scheduler_watchdog_tick()
    resume.assert_not_called()
    assert out["enabled"] is False
    assert out["overdue_count"] == 5


def test_watchdog_holds_resume_on_send_failure_signature():
    # Overdue persists across the streak, queue empty, both post workers alive: the sends
    # are failing (not the queue stalling). The breaker holds resume and defers to per-row
    # auto-pause instead of churning purge+re-enqueue.
    sh.reset_scheduler_watchdog_state()
    sched = {
        "beat_running": True,
        "celery_post_worker_running": True,
        "celery_post_scheduler_worker_running": True,
    }
    stack, _ = _watchdog_env(overdue=3, post_len=0, sched=sched)
    with stack:
        with patch(
            "app.services.post_scheduler.scheduled_drain_snapshot",
            return_value={"due_len": 0, "scheduler_queue": 0},
        ), patch("app.services.post_scheduler.resume_scheduled_posting") as resume:
            # Prime the overdue streak past the breaker threshold (default 2).
            sh._WATCHDOG_OVERDUE_STREAK = sh._watchdog_send_failure_streak()
            out = sh.scheduler_watchdog_tick()
    resume.assert_not_called()
    assert any(a["action"] == "send_failure_hold" for a in out["actions"])


def test_watchdog_resumes_when_worker_down_even_if_queue_empty():
    # Same empty-queue / overdue shape, but the scheduler worker is DOWN — that is a stall,
    # not a send failure. The breaker must not fire; resume still runs.
    sh.reset_scheduler_watchdog_state()
    sched = {
        "beat_running": True,
        "celery_post_worker_running": True,
        "celery_post_scheduler_worker_running": False,
    }
    stack, _ = _watchdog_env(overdue=3, post_len=0, sched=sched)
    with stack:
        with patch(
            "app.services.post_scheduler.scheduled_drain_snapshot",
            return_value={"due_len": 0, "scheduler_queue": 0},
        ), patch(
            "app.services.post_scheduler.resume_scheduled_posting",
            return_value={"ok": True},
        ) as resume:
            sh._WATCHDOG_OVERDUE_STREAK = sh._watchdog_send_failure_streak()
            out = sh.scheduler_watchdog_tick()
    resume.assert_called_once_with(purge_post_queue=True)
    assert not any(a["action"] == "send_failure_hold" for a in out["actions"])


def test_fast_snapshot_uses_cache_and_never_scans():
    sh.reset_scheduler_watchdog_state()
    with patch(
        "app.services.system_health.cached_scheduling_health",
        return_value={"beat_running": True, "celery_post_scheduler_worker_running": True},
    ):
        with patch("app.services.post_scheduler._post_queue_length", return_value=4):
            with patch(
                "app.services.post_scheduler.schedulers_stall_summary",
                return_value={"count": 1},
            ):
                with patch(
                    "app.services.focus_profile.get_focus_state",
                    return_value={"profile": "off"},
                ):
                    # Guard: any powershell process scan must blow up the test.
                    with patch(
                        "app.services.system_health._win_leaf_worker_count",
                        side_effect=AssertionError("fast path must not scan processes"),
                    ):
                        snap = sh.scheduling_fast_snapshot()
    assert snap["beat_up"] is True
    assert snap["celery_post_up"] is True
    assert snap["post_queue_depth"] == 4
    assert snap["overdue_count"] == 1
    assert snap["focus"] == "off"


def test_auto_remediate_no_longer_owns_post_queue_lane():
    sh.reset_scheduler_watchdog_state()
    health = {"ok": False, "conflicts": [{"code": "schedulers_overdue"}]}
    with patch("app.services.system_health.collect_system_health", return_value=health):
        with patch("app.services.system_health.health_auto_remediate_enabled", return_value=True):
            with patch("app.services.system_health._auto_remediate_cooldown_ok", return_value=True):
                with patch("app.services.focus_profile.sync_focus_flags_from_profile"):
                    with patch(
                        "app.services.focus_profile.get_focus_state",
                        return_value={"profile": "off"},
                    ):
                        with patch(
                            "app.services.focus_profile.pause_beat_scheduling",
                            return_value=False,
                        ):
                            with patch(
                                "app.services.system_health.remediate_system_issues"
                            ) as remediate:
                                out = sh.auto_remediate_health_conflicts()
    # schedulers_overdue is now the watchdog's job — auto_remediate must not resume.
    remediate.assert_not_called()
    assert out["auto_fixed"] == []
