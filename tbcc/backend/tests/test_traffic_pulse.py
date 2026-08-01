"""Traffic Pulse — instant cap and digest buffer."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.services.traffic_pulse import (
    clear_digest_buffer,
    push_traffic_pulse,
    traffic_pulse_instant_hourly_cap,
)


@pytest.fixture(autouse=True)
def _clear_digest():
    clear_digest_buffer()
    yield
    clear_digest_buffer()


def test_instant_cap_downgrades_to_digest(monkeypatch):
    monkeypatch.setenv("TBCC_TRAFFIC_PULSE_ENABLED", "1")
    monkeypatch.setenv("TBCC_TRAFFIC_PULSE_INSTANT", "beacon")
    monkeypatch.setenv("TBCC_TRAFFIC_PULSE_INSTANT_HOURLY_CAP", "2")

    mock_redis = MagicMock()
    state = {"count": 0, "bucket": 0}

    def _get(key):
        if "bucket" in key:
            return state["bucket"]
        return state["count"]

    def _incr(key):
        state["count"] += 1
        return state["count"]

    mock_redis.get.side_effect = _get
    mock_redis.incr.side_effect = _incr
    mock_redis.set = MagicMock()
    monkeypatch.setattr("app.services.traffic_pulse._redis", lambda: mock_redis)

    with patch("app.services.admin_inbox.push_admin_inbox_event") as push:
        push_traffic_pulse("beacon", title="a", body="1")
        push_traffic_pulse("beacon", title="b", body="2")
        push_traffic_pulse("beacon", title="c", body="3")
        instant_calls = [c.kwargs.get("instant") for c in push.call_args_list]
        assert instant_calls == [True, True, False]
        assert mock_redis.hincrby.called


def test_affiliate_primary_fallback_uses_undress(monkeypatch):
    monkeypatch.delenv("TBCC_AFFILIATE_UNDRESS_URL", raising=False)
    from app.services.aof_social_links import affiliate_primary_fallback_url

    url = affiliate_primary_fallback_url()
    assert "nodress" in url.lower() or "undress" in url.lower()
