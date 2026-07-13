"""Idle Service Governor: gate fail-open, tick desired-state, idle-window hysteresis."""

from unittest.mock import patch

from app.services import idle_service_governor as isg


class _FakeRedis:
    def __init__(self):
        self.store = {}
        self.ex = {}

    def get(self, k):
        return self.store.get(k)

    def set(self, k, v, ex=None):
        self.store[k] = v
        self.ex[k] = ex


def _active_key(name: str) -> str:
    return isg._KEY_ACTIVE.format(name=name)


def test_gate_pass_through_when_disabled():
    # Governor off => gate is a pure pass-through even if Redis says "0".
    fake = _FakeRedis()
    fake.store[_active_key("export_flywheel")] = "0"
    with patch.object(isg, "_redis_client", return_value=fake), patch.object(
        isg, "governor_enabled", return_value=False
    ):
        assert isg.governed_service_active("export_flywheel") is True


def test_gate_reads_desired_state_when_enabled():
    fake = _FakeRedis()
    with patch.object(isg, "_redis_client", return_value=fake), patch.object(
        isg, "governor_enabled", return_value=True
    ):
        # Missing key => fail-open (never strand).
        assert isg.governed_service_active("income_poll") is True
        fake.store[_active_key("income_poll")] = "0"
        assert isg.governed_service_active("income_poll") is False
        fake.store[_active_key("income_poll")] = "1"
        assert isg.governed_service_active("income_poll") is True


def test_tick_sets_active_on_wake_and_persists():
    fake = _FakeRedis()
    svc = isg.GovernedService(
        name="t1", idle_minutes_env="X_UNSET", idle_minutes_default=60, wake=lambda db: True
    )
    with patch.object(isg, "_redis_client", return_value=fake), patch.object(
        isg, "governor_enabled", return_value=True
    ), patch.object(isg, "GOVERNED_SERVICES", {"t1": svc}), patch.object(
        isg, "_ops_worker_up", return_value=True
    ), patch.object(isg, "time") as tmock:
        tmock.time.return_value = 1000.0
        out = isg.governor_tick(force=True)
    assert out["states"]["t1"] is True
    assert fake.store[_active_key("t1")] == "1"
    assert out["ops_worker_up"] is True


def test_tick_idle_window_hysteresis():
    fake = _FakeRedis()
    wake_state = {"v": True}
    svc = isg.GovernedService(
        name="t2",
        idle_minutes_env="X_UNSET_IDLE",
        idle_minutes_default=10,
        wake=lambda db: wake_state["v"],
    )
    with patch.object(isg, "_redis_client", return_value=fake), patch.object(
        isg, "governor_enabled", return_value=True
    ), patch.object(isg, "GOVERNED_SERVICES", {"t2": svc}), patch.object(
        isg, "_ops_worker_up", return_value=None
    ), patch.object(isg, "time") as tmock:
        tmock.time.return_value = 1000.0
        isg.governor_tick(force=True)  # wake -> active, last_activity=1000
        assert fake.store[_active_key("t2")] == "1"

        wake_state["v"] = False
        tmock.time.return_value = 1000.0 + 5 * 60  # 5 min < 10 min window
        isg.governor_tick(force=True)
        assert fake.store[_active_key("t2")] == "1"  # hysteresis: still active

        tmock.time.return_value = 1000.0 + 11 * 60  # 11 min > 10 min window
        isg.governor_tick(force=True)
        assert fake.store[_active_key("t2")] == "0"  # now idle


def test_activity_touch_persists_without_early_ttl():
    # The idle window (up to 7d) is enforced by time math, not TTL — the activity key must not
    # expire early or long windows (erome_view_sync 72h) truncate to the TTL.
    fake = _FakeRedis()
    with patch.object(isg, "_redis_client", return_value=fake), patch.object(
        isg, "time"
    ) as tmock:
        tmock.time.return_value = 1000.0
        isg.touch_service_activity("erome_view_sync")
    key = isg._KEY_LAST_ACTIVITY.format(name="erome_view_sync")
    assert fake.store[key] == "1000.0"
    assert fake.ex[key] is None


def test_income_poll_not_governed():
    # Default-on with no wake producer — must not be under governance (would idle it forever).
    assert "income_poll" not in isg.GOVERNED_SERVICES


def test_tick_disabled_is_noop():
    with patch.object(isg, "governor_enabled", return_value=False):
        out = isg.governor_tick()
    assert out == {"ok": True, "enabled": False}


def test_flywheel_task_skips_when_governed_idle():
    with patch(
        "app.services.idle_service_governor.governed_service_active", return_value=False
    ), patch("app.services.export_flywheel_service.flywheel_enabled", return_value=True):
        from app.workers.export_flywheel_worker import export_flywheel_tick

        out = export_flywheel_tick()
    assert out["skipped"] == "governed_idle"
