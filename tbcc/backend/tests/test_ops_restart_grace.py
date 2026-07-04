"""Backend restart grace suppresses ops toasts during expected API downtime."""

from unittest.mock import patch

from app.services import ops_restart_grace


def test_mark_and_clear_grace(monkeypatch):
    store: dict[str, str] = {}

    class FakeRedis:
        def set(self, key, val, ex=None):
            store[key] = str(val)

        def get(self, key):
            return store.get(key)

        def delete(self, key):
            store.pop(key, None)

    monkeypatch.setattr(ops_restart_grace, "_redis_client", lambda: FakeRedis())
    assert ops_restart_grace.backend_restart_grace_active() is False
    ops_restart_grace.mark_backend_restart_grace(seconds=60)
    assert ops_restart_grace.backend_restart_grace_active() is True
    ops_restart_grace.clear_backend_restart_grace(tail_seconds=0)
    assert ops_restart_grace.backend_restart_grace_active() is False


def test_poll_ops_alerts_empty_during_grace():
    from app.services.ops_alerts import poll_ops_alerts

    with patch("app.services.ops_restart_grace.backend_restart_grace_active", return_value=True):
        with patch("app.services.ops_restart_grace.restart_grace_public_snapshot", return_value={"active": True}):
            out = poll_ops_alerts()
    assert out["alerts"] == []
    assert out["restart_grace"]["active"] is True
