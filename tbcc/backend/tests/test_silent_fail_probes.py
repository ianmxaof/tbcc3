"""Unit tests for silent_fail_probes (no live Redis/DB)."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.silent_fail_probes import (
    _parse_exported_at,
    probe_intake_lane,
    storage_hub_r2_export_enabled,
    verdict_from_last_success,
)


def test_verdict_idle_when_disabled():
    assert (
        verdict_from_last_success(
            enabled=False, last_success_ts=None, interval_minutes=60
        )
        == "idle"
    )


def test_verdict_never_seen():
    assert (
        verdict_from_last_success(
            enabled=True, last_success_ts=None, interval_minutes=60
        )
        == "never_seen"
    )
    assert (
        verdict_from_last_success(
            enabled=True, last_success_ts=0.0, interval_minutes=60
        )
        == "never_seen"
    )


def test_verdict_ok_and_stale():
    now = 1_000_000.0
    interval = 60
    assert (
        verdict_from_last_success(
            enabled=True,
            last_success_ts=now - 30 * 60,
            interval_minutes=interval,
            now=now,
            stale_mult=2.0,
        )
        == "ok"
    )
    assert (
        verdict_from_last_success(
            enabled=True,
            last_success_ts=now - 3 * 60 * 60,
            interval_minutes=interval,
            now=now,
            stale_mult=2.0,
        )
        == "stale"
    )


def test_parse_exported_at():
    raw = json.dumps(
        {"r2": {"object_key": "library/hub/1/a.jpg", "exported_at": "2026-08-20T12:00:00+00:00"}}
    )
    ts = _parse_exported_at(raw)
    assert ts is not None and ts > 0
    assert _parse_exported_at(None) is None
    assert _parse_exported_at("{}") is None


def test_r2_enablement_island_default(monkeypatch):
    monkeypatch.delenv("TBCC_STORAGE_HUB_R2_EXPORT_ENABLED", raising=False)
    monkeypatch.setenv("TBCC_REVENUE_ISLAND_ACTIVE", "1")
    assert storage_hub_r2_export_enabled() is True
    monkeypatch.setenv("TBCC_REVENUE_ISLAND_ACTIVE", "0")
    assert storage_hub_r2_export_enabled() is False
    monkeypatch.setenv("TBCC_STORAGE_HUB_R2_EXPORT_ENABLED", "0")
    monkeypatch.setenv("TBCC_REVENUE_ISLAND_ACTIVE", "1")
    assert storage_hub_r2_export_enabled() is False


def test_probe_intake_lane_never_seen(monkeypatch):
    monkeypatch.setenv("TBCC_INTAKE_SCHEDULER_ENABLED", "1")
    monkeypatch.setenv("TBCC_INTAKE_INTERVAL_MIN", "60")

    fake = MagicMock()
    store: dict[str, str] = {}

    fake.get.side_effect = store.get
    fake.set.side_effect = lambda k, v, ex=None: store.__setitem__(k, v)
    monkeypatch.setattr("app.services.intake_scheduler._redis", lambda: fake)

    out = probe_intake_lane("inbox", now=1_000_000.0)
    assert out["verdict"] == "never_seen"
    assert out["enabled"] is True
    assert out["stop_kind"] == "redis"


def test_probe_intake_lane_idle_when_off(monkeypatch):
    monkeypatch.setenv("TBCC_INTAKE_SCHEDULER_ENABLED", "0")
    monkeypatch.delenv("TBCC_STORAGE_POOL_SEED_ENABLED", raising=False)
    fake = MagicMock()
    fake.get.return_value = None
    monkeypatch.setattr("app.services.intake_scheduler._redis", lambda: fake)

    out = probe_intake_lane("inbox")
    assert out["verdict"] == "idle"


def test_probe_r2_export_never_seen(monkeypatch):
    from app.services import silent_fail_probes as sfp

    monkeypatch.setenv("TBCC_STORAGE_HUB_R2_EXPORT_ENABLED", "1")
    monkeypatch.setenv("TBCC_STORAGE_HUB_R2_EXPORT_MINUTES", "10")
    monkeypatch.setattr(sfp, "latest_r2_exported_at_ts", lambda db, sample=80: None)
    monkeypatch.setattr(sfp, "count_hub_missing_r2_sample", lambda db, limit=20: 3)
    monkeypatch.setattr(sfp, "get_storage_hub_r2_last_tick_ts", lambda: 0.0)

    out = sfp.probe_storage_hub_r2_export(SimpleNamespace())
    assert out["verdict"] == "never_seen"
    assert out["beat_key"] == "storage-hub-r2-export"
    assert out["pending_missing_sample"] == 3


def test_probe_r2_export_ok_on_recent_tick_despite_old_export(monkeypatch):
    """Beat firing with failed downloads must not look like 'never fired'."""
    from app.services import silent_fail_probes as sfp

    now = 1_000_000.0
    monkeypatch.setenv("TBCC_STORAGE_HUB_R2_EXPORT_ENABLED", "1")
    monkeypatch.setenv("TBCC_STORAGE_HUB_R2_EXPORT_MINUTES", "10")
    monkeypatch.setattr(
        sfp, "latest_r2_exported_at_ts", lambda db, sample=80: now - 10_000
    )
    monkeypatch.setattr(sfp, "count_hub_missing_r2_sample", lambda db, limit=20: 4)
    monkeypatch.setattr(sfp, "get_storage_hub_r2_last_tick_ts", lambda: now - 60)

    out = sfp.probe_storage_hub_r2_export(SimpleNamespace(), now=now, stale_mult=3.0)
    assert out["verdict"] == "ok"
    assert out["export_lag"] is True
    assert out["pending_missing_sample"] == 4


def test_probe_enrich_backlog_idle_when_off(monkeypatch):
    from app.services import silent_fail_probes as sfp

    monkeypatch.setenv("TBCC_ENRICH_BACKLOG_SWEEP", "0")
    out = sfp.probe_enrich_backlog()
    assert out["verdict"] == "idle"
    assert out["beat_key"] == "enrich-backlog-sweep"


def test_probe_enrich_backlog_never_seen(monkeypatch):
    from app.services import enrich_backlog as eb
    from app.services import silent_fail_probes as sfp

    monkeypatch.setenv("TBCC_ENRICH_BACKLOG_SWEEP", "1")
    monkeypatch.setenv("TBCC_ENRICH_BACKLOG_INTERVAL_MIN", "10")
    monkeypatch.setattr(eb, "get_last_success_ts", lambda: 0.0)

    out = sfp.probe_enrich_backlog(now=1_000_000.0)
    assert out["verdict"] == "never_seen"
    assert out["stop_kind"] == "redis"
