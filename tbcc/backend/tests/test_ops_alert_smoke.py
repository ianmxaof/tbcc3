"""Smoke tests for ops alert parsing end-to-end."""

from __future__ import annotations

from app.services.ops_alerts import _parse_hub_alert


def test_parse_session_lock_names_scheduler(monkeypatch):
    monkeypatch.setattr(
        "app.services.error_suggestions._lookup_scheduled_post_names",
        lambda ids: ["AOF MILF SCHEDULER"] if 2 in ids else [],
    )
    monkeypatch.setattr(
        "app.services.error_suggestions._lookup_inflight_post_ids",
        lambda: [],
    )
    monkeypatch.setattr("app.services.focus_profile.count_active_import_jobs", lambda: 0)

    line = (
        "[2026-06-25T12:00:00Z] [tbcc-celery-post] [ERROR] "
        "Post scheduled text failed for AOF MILF SCHEDULER: database is locked"
    )
    alert = _parse_hub_alert(line)
    assert alert is not None
    assert alert["title"] == "AOF MILF SCHEDULER blocked"
    assert "AOF MILF SCHEDULER" in alert["message"]
    assert "Trim duplicate workers" in alert["message"]
    assert alert.get("scheduler_names") == ["AOF MILF SCHEDULER"]


def test_parse_pool_failure_names_pool(monkeypatch):
    monkeypatch.setattr(
        "app.services.error_suggestions._lookup_pool_names",
        lambda ids: ["AOF ASS POOL"] if 5 in ids else [],
    )
    monkeypatch.setattr(
        "app.services.error_suggestions._lookup_inflight_post_ids",
        lambda: [],
    )

    line = (
        "[2026-06-25T12:00:00Z] [tbcc-celery-post] [ERROR] "
        "Post pool failed for AOF ASS POOL: database is locked"
    )
    alert = _parse_hub_alert(line)
    assert alert is not None
    assert "AOF ASS POOL" in alert["title"]
    assert "Trim duplicate workers" in alert["message"] or "Celery-Post" in alert["message"]
