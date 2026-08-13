from app.workers.buffer_armory_worker import (
    _startup_refill_enabled,
    _worker_should_run_startup_refill,
)


def test_startup_refill_enabled_default_on(monkeypatch):
    monkeypatch.delenv("TBCC_BUFFER_ARMORY_STARTUP_REFILL", raising=False)
    assert _startup_refill_enabled()


def test_startup_refill_can_disable(monkeypatch):
    monkeypatch.setenv("TBCC_BUFFER_ARMORY_STARTUP_REFILL", "0")
    assert not _startup_refill_enabled()


def test_worker_should_run_startup_refill_main_worker():
    assert _worker_should_run_startup_refill("island@hostname")
    assert _worker_should_run_startup_refill("celery@KaiUlew")


def test_worker_should_not_run_startup_refill_post_worker():
    assert not _worker_should_run_startup_refill("island-post@hostname")
    assert not _worker_should_run_startup_refill("scheduler@hostname")
