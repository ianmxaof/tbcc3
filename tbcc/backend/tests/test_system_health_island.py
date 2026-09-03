"""Island / Docker scheduling health heuristics."""

from unittest.mock import patch

from app.services import system_health as sh


def _fake_counts(pong: dict[str, dict]):
    class _FakeInspect:
        def ping(self):
            return pong

    class _FakeControl:
        def inspect(self, timeout=0):
            return _FakeInspect()

    class _FakeCelery:
        control = _FakeControl()

    with patch("app.workers.celery_app.celery", _FakeCelery()):
        return sh._celery_inspect_scheduling_counts()


def test_island_post_worker_implies_main_worker_when_solo_busy(monkeypatch):
    monkeypatch.setenv("TBCC_REVENUE_ISLAND_ACTIVE", "1")
    counts = _fake_counts({"island-post@container": {"ok": "pong"}})
    assert counts is not None
    assert counts["celery_post"] == 1
    assert counts["celery_worker"] == 1
    assert counts["beat"] == 1


def test_island_main_worker_classified_by_name(monkeypatch):
    monkeypatch.setenv("TBCC_REVENUE_ISLAND_ACTIVE", "1")
    counts = _fake_counts(
        {
            "island@container": {"ok": "pong"},
            "island-post@container": {"ok": "pong"},
        }
    )
    assert counts is not None
    assert counts["celery_worker"] == 1
    assert counts["celery_post"] == 1


def test_island_tg_worker_not_counted_as_celery_duplicate(monkeypatch):
    """island-tg@ consumes telegram queue only — must not trip celery_worker_duplicate."""
    monkeypatch.setenv("TBCC_REVENUE_ISLAND_ACTIVE", "1")
    counts = _fake_counts(
        {
            "island@container": {"ok": "pong"},
            "island-tg@container": {"ok": "pong"},
            "island-post@container": {"ok": "pong"},
        }
    )
    assert counts is not None
    assert counts["celery_worker"] == 1
    assert counts["celery_post"] == 1
    assert counts["beat"] == 1


def test_island_worker_implies_celery_ops_when_revenue_island(monkeypatch):
    """island@ (-Q celery,subscription,ops_growth,ops_relay) never answers as "ops@" —
    celery_ops must not report a false red just because no worker is hostname-tagged ops.
    """
    monkeypatch.setenv("TBCC_REVENUE_ISLAND_ACTIVE", "1")
    counts = _fake_counts(
        {
            "island@container": {"ok": "pong"},
            "island-post@container": {"ok": "pong"},
        }
    )
    assert counts is not None
    assert counts["celery_worker"] == 1
    assert counts["celery_post"] == 1
    assert counts["celery_ops"] >= 1


def test_island_worker_absent_does_not_imply_celery_ops(monkeypatch):
    """Only the telegram-queue worker answers ⇒ no main worker up ⇒ celery_ops stays 0."""
    monkeypatch.setenv("TBCC_REVENUE_ISLAND_ACTIVE", "1")
    counts = _fake_counts({"island-tg@container": {"ok": "pong"}})
    assert counts is not None
    assert counts["celery_worker"] == 0
    assert counts["celery_ops"] == 0


def test_celery_ops_not_inferred_off_island(monkeypatch):
    """Off the revenue island (TBCC_REVENUE_ISLAND_ACTIVE unset), do not infer ops from
    the main worker — only an explicit ops@/ops_growth hostname counts."""
    monkeypatch.delenv("TBCC_REVENUE_ISLAND_ACTIVE", raising=False)
    counts = _fake_counts({"island@container": {"ok": "pong"}})
    assert counts is not None
    assert counts["celery_worker"] == 1
    assert counts["celery_ops"] == 0
