"""Ops alert poll must not return unbounded hub/error toasts."""

from __future__ import annotations

from app.services.ops_alerts import _apply_client_poll_limits, _collapse_hub_alerts


def test_collapse_hub_alerts_digest():
    alerts = [
        {"id": f"hub:{i}", "kind": "error_hub", "severity": "warning", "title": f"E{i}", "message": "x"}
        for i in range(5)
    ]
    out = _collapse_hub_alerts(alerts)
    assert len(out) == 1
    assert out[0]["code"] == "error_hub_digest"
    assert "5 error-hub" in out[0]["message"]


def test_apply_client_poll_limits_blocks_hub_by_default(monkeypatch):
    monkeypatch.setattr("app.services.ops_alerts.hub_toast_enabled", lambda: False)
    monkeypatch.setattr("app.services.ops_alerts.max_client_toasts_per_2min", lambda: 1)
    monkeypatch.setattr("app.services.ops_alerts._client_toast_rate_ok", lambda **_: True)
    alerts = [
        {"id": "hub:1", "kind": "error_hub", "code": "error_hub", "severity": "critical", "title": "X"},
        {"id": "conflict:redis", "kind": "conflict", "code": "redis_down", "severity": "critical", "title": "Redis"},
    ]
    out = _apply_client_poll_limits(alerts)
    assert len(out) == 1
    assert out[0]["kind"] == "conflict"
