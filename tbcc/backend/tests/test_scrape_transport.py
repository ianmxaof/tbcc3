"""Scrape transport: cancel / skip / overview."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.models.content_pool import ContentPool
from app.models.source import Source
from app.services import scrape_run_service as svc


def _utc_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


@pytest.fixture()
def pool(db):
    p = ContentPool(name="Test Pool")
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


@pytest.fixture()
def source(db, pool):
    s = Source(
        name="MEGAS",
        source_type="telegram_channel",
        identifier="-1003320000000",
        pool_id=pool.id,
        active=True,
        schedule_enabled=True,
        schedule_cron="0 */6 * * *",
        media_types="both",
        max_messages_per_run=50,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def test_cancel_queued_run(db, source):
    run = svc.create_scrape_run(db, source, trigger="manual", celery_task_id="task-abc")
    with patch.object(svc, "request_scrape_cancel"), patch.object(svc, "release_scrape_lock"), patch(
        "app.workers.celery_app.celery"
    ) as celery_mod:
        celery_mod.control.revoke = MagicMock()
        out = svc.cancel_scrape_run(db, run.id)
    assert out["ok"] is True
    assert out["status"] == "cancelled"
    db.refresh(run)
    assert run.status == "cancelled"
    assert run.error_summary


def test_skip_active_queues_next(db, pool, source):
    other = Source(
        name="NextChan",
        source_type="telegram_channel",
        identifier="@next",
        pool_id=pool.id,
        active=True,
        schedule_enabled=True,
        schedule_cron="0 */6 * * *",
        media_types="both",
        max_messages_per_run=50,
    )
    db.add(other)
    db.commit()
    db.refresh(other)

    run = svc.create_scrape_run(db, source, trigger="manual")
    run.status = "running"
    run.started_at = _utc_naive() - timedelta(hours=2)
    db.commit()

    with patch.object(svc, "cancel_scrape_run", return_value={"ok": True, "run_id": run.id, "status": "cancelled"}) as cancel_mock, patch(
        "app.workers.scraper_worker.run_scrape"
    ) as run_scrape:
        run_scrape.delay = MagicMock(return_value=MagicMock(id="celery-next"))
        # Force candidates via sources_due empty → fallback by id
        with patch.object(svc, "sources_due_for_cron", return_value=[]):
            out = svc.skip_active_scrape(db, queue_next=True)

    cancel_mock.assert_called_once()
    assert out["queued_next"] is not None
    assert out["queued_next"]["source_id"] == other.id


def test_transport_overview_phases(db, source):
    run = svc.create_scrape_run(db, source, trigger="manual")
    run.status = "failed"
    run.error_summary = "Telethon scraper session error."
    run.finished_at = _utc_naive()
    db.commit()

    overview = svc.scrape_transport_overview(db)
    assert overview["counts"]["total"] >= 1
    row = next(r for r in overview["sources"] if r["source_id"] == source.id)
    assert row["phase"] == "error"
    assert row["pool_name"]
    assert row["latest_run"]["status"] == "failed"


def test_stalled_running_phase(db, source):
    run = svc.create_scrape_run(db, source, trigger="manual")
    run.status = "running"
    run.started_at = _utc_naive() - timedelta(hours=3)
    db.commit()
    overview = svc.scrape_transport_overview(db)
    row = next(r for r in overview["sources"] if r["source_id"] == source.id)
    assert row["phase"] == "stalled"
