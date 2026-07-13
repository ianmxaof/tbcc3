"""Tray service toggle parity between supervisor and health auto-remediate."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services import system_health as sh


def test_service_user_enabled_defaults_lean(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(sh, "_tbcc_root", lambda: tmp_path)
    monkeypatch.delenv("TBCC_STACK_PROFILE", raising=False)
    assert sh.service_user_enabled("backend") is True
    assert sh.service_user_enabled("celery") is True
    assert sh.service_user_enabled("admin") is False


def test_service_user_enabled_respects_toggle_file(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(sh, "_tbcc_root", lambda: tmp_path)
    run_dir = tmp_path / ".tbcc-run"
    run_dir.mkdir(parents=True)
    (run_dir / "service-toggles.json").write_text(
        json.dumps(
            {
                "celery": False,
                "beat": False,
                "celery_post": False,
                "celery_post_scheduler": False,
                "backend": True,
            }
        ),
        encoding="utf-8",
    )
    assert sh.service_user_enabled("celery") is False
    assert sh.scheduling_stack_user_enabled() is False


def test_start_tbcc_stack_services_skips_disabled(monkeypatch):
    monkeypatch.setattr(sh, "service_user_enabled", lambda _sid: False)
    out = sh.start_tbcc_stack_services(["beat", "celery"])
    assert out["ok"] is True
    assert out.get("skipped") == "all_services_disabled_in_tray"


def test_auto_remediate_skips_scheduling_when_tray_disabled(monkeypatch):
    health = {
        "ok": False,
        "conflicts": [{"code": "celery_worker_down"}, {"code": "beat_down"}],
    }
    monkeypatch.setattr(sh, "collect_system_health", lambda: health)
    monkeypatch.setattr(sh, "health_auto_remediate_enabled", lambda: True)
    monkeypatch.setattr(sh, "scheduling_stack_user_enabled", lambda: False)
    monkeypatch.setattr(sh, "_auto_remediate_cooldown_ok", lambda _code: True)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("app.services.focus_profile.sync_focus_flags_from_profile", lambda: None)
        mp.setattr(
            "app.services.focus_profile.get_focus_state",
            lambda: {"profile": "off"},
        )
        mp.setattr("app.services.focus_profile.pause_beat_scheduling", lambda: False)
        out = sh.auto_remediate_health_conflicts()
    assert out.get("auto_fixed", []) == []
