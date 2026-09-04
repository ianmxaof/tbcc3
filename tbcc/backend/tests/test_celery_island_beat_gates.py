"""Revenue-island Beat gates + network_liveness registration."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from app.workers.celery_app import celery


def test_network_liveness_worker_is_included_and_registered():
    import app.workers.network_liveness_worker  # noqa: F401 — register tasks

    assert "app.workers.network_liveness_worker" in (celery.conf.include or [])
    assert "app.workers.storage_auto_pipe_worker" in (celery.conf.include or [])
    assert celery.conf.task_routes.get("app.workers.storage_auto_pipe_worker.*") == {
        "queue": "telegram"
    }
    assert "app.workers.network_liveness_worker.post_milestone_fomo" in celery.tasks


def test_storage_lane_drain_worker_is_included_and_registered():
    """Ship gate (island-ops-empty-pools Phase 1b): the drain button enqueues a task
    that must actually be known to a worker — not just present on disk."""
    import app.workers.storage_lane_drain_worker  # noqa: F401 — register tasks

    assert "app.workers.storage_lane_drain_worker" in (celery.conf.include or [])
    assert celery.conf.task_routes.get("app.workers.storage_lane_drain_worker.*") == {
        "queue": "telegram"
    }
    assert "app.workers.storage_lane_drain_worker.run_lane_drain" in celery.tasks


def test_env_flag_and_revenue_island_helpers(monkeypatch):
    from app.workers import celery_app as m

    monkeypatch.delenv("TBCC_REVENUE_ISLAND_ACTIVE", raising=False)
    assert m._env_flag("TBCC_REVENUE_ISLAND_ACTIVE", "0") is False
    monkeypatch.setenv("TBCC_REVENUE_ISLAND_ACTIVE", "1")
    assert m._revenue_island_active() is True
    monkeypatch.setenv("TBCC_REVENUE_ISLAND_ACTIVE", "false")
    assert m._revenue_island_active() is False


def _fresh_beat_keys(island: bool) -> set[str]:
    """Import celery_app in a clean process so module-level Beat gates re-evaluate."""
    backend = Path(__file__).resolve().parents[1]
    env = {k: v for k, v in os.environ.items() if not k.startswith("TBCC_")}
    env["PYTHONPATH"] = str(backend)
    env["TBCC_REVENUE_ISLAND_ACTIVE"] = "1" if island else "0"
    script = (
        "from app.workers.celery_app import celery\n"
        "print('\\n'.join(sorted((celery.conf.beat_schedule or {}).keys())))\n"
    )
    out = subprocess.check_output(
        [sys.executable, "-c", script],
        cwd=str(backend),
        env=env,
        text=True,
    )
    return {line.strip() for line in out.splitlines() if line.strip()}


def test_island_beat_optional_defaults():
    keys = _fresh_beat_keys(island=True)
    assert "scrape-scheduler-tick" not in keys
    assert "market-intel-probe" not in keys
    assert "storage-hub-r2-export" in keys
    assert "aof-milestone-fomo" in keys


def test_home_beat_optional_defaults():
    keys = _fresh_beat_keys(island=False)
    assert "scrape-scheduler-tick" in keys
    assert "market-intel-probe" in keys
    assert "storage-hub-r2-export" not in keys
    assert "aof-milestone-fomo" in keys
