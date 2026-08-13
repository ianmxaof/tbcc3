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
