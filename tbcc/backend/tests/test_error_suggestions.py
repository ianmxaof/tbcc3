"""Tests for user-facing ops alert copy."""

from __future__ import annotations

from app.services.error_suggestions import (
    format_hub_alert_message,
    hub_alert_user_copy,
    resolve_hub_alert_context,
)


def test_session_lock_copy_names_scheduler(monkeypatch):
    monkeypatch.setattr(
        "app.services.error_suggestions._lookup_scheduled_post_names",
        lambda ids: ["AOF MILF SCHEDULER"] if 7 in ids else [],
    )
    monkeypatch.setattr(
        "app.services.error_suggestions._lookup_inflight_post_ids",
        lambda: [],
    )

    ctx = resolve_hub_alert_context(
        "session_sqlite_lock",
        "Post scheduled text failed for AOF MILF SCHEDULER: database is locked",
        "tbcc-celery-post",
    )
    copy = hub_alert_user_copy(
        "session_sqlite_lock",
        "Post scheduled text failed for AOF MILF SCHEDULER: database is locked",
        "tbcc-celery-post",
        context=ctx,
    )

    assert copy["title"] == "AOF MILF SCHEDULER blocked"
    assert "AOF MILF SCHEDULER" in (copy.get("impact") or "")
    assert "Trim duplicate workers" in (copy.get("action") or "")


def test_session_lock_uses_inflight_when_no_post_id_in_body(monkeypatch):
    monkeypatch.setattr(
        "app.services.error_suggestions._lookup_inflight_post_ids",
        lambda: [3],
    )
    monkeypatch.setattr(
        "app.services.error_suggestions._lookup_scheduled_post_names",
        lambda ids: ["AOF ASS SCHEDULER"] if 3 in ids else [],
    )

    ctx = resolve_hub_alert_context(
        "session_sqlite_lock",
        "database is locked",
        "tbcc-celery-post",
    )
    copy = hub_alert_user_copy("session_sqlite_lock", "database is locked", "tbcc-celery-post", context=ctx)

    assert copy["title"] == "AOF ASS SCHEDULER blocked"


def test_format_hub_alert_message_includes_action_steps():
    copy = {
        "title": "AOF MILF SCHEDULER blocked",
        "impact": "Scheduler: AOF MILF SCHEDULER\ncould not send.",
        "action": "1) Dashboard health\n2) Restart Celery-Post",
    }
    msg = format_hub_alert_message(copy)
    assert "What to do:" in msg
    assert "1) Dashboard health" in msg


def test_pool_post_failed_copy(monkeypatch):
    monkeypatch.setattr(
        "app.services.error_suggestions._lookup_pool_names",
        lambda ids: ["AOF MILF POOL"] if 12 in ids else [],
    )
    monkeypatch.setattr(
        "app.services.error_suggestions._lookup_inflight_post_ids",
        lambda: [],
    )

    body = "Post pool failed for AOF MILF POOL: ConnectionError"
    ctx = resolve_hub_alert_context("service_traceback", body, "tbcc-celery-post")
    copy = hub_alert_user_copy("service_traceback", body, "tbcc-celery-post", context=ctx)

    assert copy["title"] == "AOF MILF POOL pool post failed"
    assert "AOF MILF POOL" in (copy.get("impact") or "")
