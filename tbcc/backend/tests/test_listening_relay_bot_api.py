"""Phase 5a — listening relay Bot API transport."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.models.channel import Channel
from app.models.listening_relay_post_log import ListeningRelayPostLog
from app.services.listening_relay_bot_send import send_listening_relay_via_bot_api
from app.services.listening_relay_compose import RelayOutbound
from app.services.listening_relay_history import queue_listening_relay_post
from app.services.telegram_bot_api import relay_use_bot_api
from app.workers.celery_app import celery


def _queue_for(task_name: str) -> str:
    route = celery.amqp.router.route({}, task_name) or {}
    q = route.get("queue")
    if q is None:
        return celery.conf.task_default_queue or "celery"
    return getattr(q, "name", q)


def test_relay_bot_api_task_on_ops_relay_queue():
    assert (
        _queue_for("app.workers.listening_relay_worker.post_listening_relay_bot_api")
        == "ops_relay"
    )


def test_relay_use_bot_api_env(monkeypatch):
    monkeypatch.delenv("TBCC_RELAY_USE_BOT_API", raising=False)
    assert relay_use_bot_api() is False
    monkeypatch.setenv("TBCC_RELAY_USE_BOT_API", "1")
    assert relay_use_bot_api() is True


@patch("app.services.listening_relay_bot_send.tg_post_with_token")
@patch("app.services.listening_relay_bot_send.resolve_bot_token_raw", return_value="tok")
def test_send_main_with_thread_and_text_followup(mock_token, mock_post, db):
    mock_post.side_effect = [
        {"ok": True, "result": {"message_id": 100}},
        {"ok": True, "result": {"message_id": 101}},
    ]
    ch = Channel(id=7, name="Voyeur", identifier="-1001234567890")
    db.add(ch)
    db.commit()

    out = send_listening_relay_via_bot_api(
        db,
        channel_id=7,
        html_body="<b>Artist</b> — Title",
        message_thread_id=42,
        send_silent=True,
        copy_followups_json='[{"html":"<pre>copy</pre>","buttons":[],"media_ids":[]}]',
    )
    assert out["ok"] is True
    assert out["message_id"] == 101
    assert out["followups_sent"] == 1

    main_call = mock_post.call_args_list[0]
    assert main_call[0][0] == "sendMessage"
    assert main_call[0][1]["message_thread_id"] == 42
    assert main_call[0][1]["disable_notification"] is True

    follow_call = mock_post.call_args_list[1]
    assert follow_call[0][1]["reply_to_message_id"] == 100


@patch("app.services.listening_relay_bot_send.tg_post_with_token")
@patch("app.services.listening_relay_bot_send.resolve_bot_token_raw", return_value="tok")
def test_send_skips_media_followup(mock_token, mock_post, db):
    mock_post.return_value = {"ok": True, "result": {"message_id": 50}}
    ch = Channel(id=1, name="Lane", identifier="@lane")
    db.add(ch)
    db.commit()

    out = send_listening_relay_via_bot_api(
        db,
        channel_id=1,
        html_body="main",
        message_thread_id=None,
        send_silent=False,
        copy_followups_json='[{"html":"x","media_ids":[99],"buttons":[]}]',
    )
    assert out["ok"] is True
    assert mock_post.call_count == 1
    assert "media_followups_deferred=1" in out.get("notes", [])


@patch("app.services.telegram_bot_api.relay_use_bot_api", return_value=True)
def test_queue_routes_to_bot_api_task(mock_flag, db):
    ch = Channel(id=3, name="Hub", identifier="@hub")
    db.add(ch)
    db.commit()
    outbound = RelayOutbound(main_html="<b>track</b>", copy_followups=[], source="test")

    with patch(
        "app.workers.listening_relay_worker.post_listening_relay_bot_api"
    ) as bot_task:
        with patch("app.workers.poster_worker.post_listening_relay_message") as tele_task:
            with patch("app.workers.listening_relay_worker.listening_relay_social_fanout"):
                log = queue_listening_relay_post(
                    db,
                    trigger="test",
                    channel_id=3,
                    message_thread_id=None,
                    random_lane=False,
                    outbound=outbound,
                    send_silent=True,
                )
    bot_task.delay.assert_called_once()
    tele_task.delay.assert_not_called()
    assert log.extra_json and '"transport":"bot_api"' in log.extra_json.replace(" ", "")


@patch("app.services.telegram_bot_api.relay_use_bot_api", return_value=False)
def test_queue_routes_to_telethon_when_flag_off(mock_flag, db):
    ch = Channel(id=4, name="Hub2", identifier="@hub2")
    db.add(ch)
    db.commit()
    outbound = RelayOutbound(main_html="hi", copy_followups=[], source="test")

    with patch(
        "app.workers.listening_relay_worker.post_listening_relay_bot_api"
    ) as bot_task:
        with patch("app.workers.poster_worker.post_listening_relay_message") as tele_task:
            with patch("app.workers.listening_relay_worker.listening_relay_social_fanout"):
                queue_listening_relay_post(
                    db,
                    trigger="test",
                    channel_id=4,
                    message_thread_id=None,
                    random_lane=False,
                    outbound=outbound,
                    send_silent=True,
                )
    tele_task.delay.assert_called_once()
    bot_task.delay.assert_not_called()


@patch("app.workers.poster_worker._acquire_poster_session_lock")
def test_bot_api_worker_does_not_acquire_poster_lock(mock_lock, db):
    from app.workers.listening_relay_worker import post_listening_relay_bot_api

    ch = Channel(id=5, name="X", identifier="@x")
    db.add(ch)
    log = ListeningRelayPostLog(trigger_kind="test", status="queued", channel_id=5)
    db.add(log)
    db.commit()
    log_id = log.id

    with patch(
        "app.services.listening_relay_bot_send.send_listening_relay_via_bot_api",
        return_value={"ok": True, "message_id": 9},
    ):
        with patch("app.workers.listening_relay_worker.SessionLocal", return_value=db):
            post_listening_relay_bot_api(5, "<b>hi</b>", None, True, None, log_id)

    mock_lock.assert_not_called()
    stored = db.query(ListeningRelayPostLog).filter(ListeningRelayPostLog.id == log_id).one()
    assert stored.status == "sent"
    assert stored.telegram_message_id == 9
