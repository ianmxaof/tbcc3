"""Tests for listening relay admission gate and bounded poster lock."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from app.models.channel import Channel
from app.models.listening_relay_post_log import ListeningRelayPostLog
from app.models.listening_relay_settings import ListeningRelaySettings
from app.services.listening_relay_admission import relay_may_send_now, relay_pause_when_scheduler_overdue
from app.workers.listening_relay_worker import poll_listening_relay_lastfm
from app.workers.poster_worker import _relay_poster_lock_timeout_s, post_listening_relay_message


def test_relay_pause_when_scheduler_overdue_default_on():
    with patch.dict("os.environ", {}, clear=False):
        assert relay_pause_when_scheduler_overdue() is True


def test_relay_pause_when_scheduler_overdue_disabled():
    with patch.dict("os.environ", {"TBCC_RELAY_PAUSE_WHEN_SCHEDULER_OVERDUE": "0"}, clear=False):
        assert relay_pause_when_scheduler_overdue() is False


def test_relay_may_send_now_when_no_overdue(db):
    with patch("app.services.listening_relay_admission.count_overdue_scheduled_posts", return_value=[]):
        assert relay_may_send_now(db) is True


def test_relay_may_send_now_blocked_when_overdue(db):
    with patch(
        "app.services.listening_relay_admission.count_overdue_scheduled_posts",
        return_value=[{"id": 1, "overdue_minutes": 12.0}],
    ):
        assert relay_may_send_now(db) is False


def test_relay_may_send_now_overdue_allowed_when_gate_off(db):
    with patch.dict("os.environ", {"TBCC_RELAY_PAUSE_WHEN_SCHEDULER_OVERDUE": "0"}, clear=False):
        with patch(
            "app.services.listening_relay_admission.count_overdue_scheduled_posts",
            return_value=[{"id": 1}],
        ):
            assert relay_may_send_now(db) is True


def test_relay_poster_lock_timeout_default():
    with patch.dict("os.environ", {}, clear=False):
        assert _relay_poster_lock_timeout_s() == 8.0


def test_relay_poster_lock_timeout_env():
    with patch.dict("os.environ", {"TBCC_RELAY_POSTER_LOCK_TIMEOUT_S": "12"}, clear=False):
        assert _relay_poster_lock_timeout_s() == 12.0


def test_poll_preserves_signature_when_schedulers_overdue(db):
    ch = Channel(id=1, name="Loot Room", identifier="@loot")
    db.add(ch)
    row = ListeningRelaySettings(
        id=1,
        enabled=True,
        channel_id=1,
        lastfm_username="user",
        lastfm_api_key="key",
        poll_interval_minutes=1,
        last_lastfm_signature="old-sig",
        last_poll_at=datetime.utcnow() - timedelta(hours=1),
    )
    db.add(row)
    db.commit()

    track = {
        "signature": "new-sig",
        "artist": "Artist",
        "title": "Track",
        "album": "Album",
        "url": "https://last.fm",
    }

    with patch("app.services.idle_service_governor.governed_service_active", return_value=True):
        with patch.object(db, "close"):
            with patch("app.workers.listening_relay_worker.SessionLocal", return_value=db):
                with patch(
                    "app.workers.listening_relay_worker.fetch_recent_track_lastfm_sync",
                    return_value=track,
                ):
                    with patch("app.workers.listening_relay_worker.relay_may_send_now", return_value=False):
                        with patch("app.workers.listening_relay_worker.queue_listening_relay_post") as queue_mock:
                            out = poll_listening_relay_lastfm()

    stored = db.query(ListeningRelaySettings).filter(ListeningRelaySettings.id == 1).one()
    assert out == {"ok": True, "skipped": "scheduler_overdue"}
    assert stored.last_lastfm_signature == "old-sig"
    queue_mock.assert_not_called()


def test_poll_queues_when_admission_allows(db):
    ch = Channel(id=1, name="Loot Room", identifier="@loot")
    db.add(ch)
    row = ListeningRelaySettings(
        id=1,
        enabled=True,
        channel_id=1,
        lastfm_username="user",
        lastfm_api_key="key",
        poll_interval_minutes=1,
        last_lastfm_signature="old-sig",
        last_poll_at=datetime.utcnow() - timedelta(hours=1),
    )
    db.add(row)
    db.commit()

    track = {
        "signature": "new-sig",
        "artist": "Artist",
        "title": "Track",
        "album": "Album",
        "url": "https://last.fm",
    }
    outbound = MagicMock(
        main_html="<b>test</b>",
        copy_followups=[],
        source="lastfm",
        source_label="Last.fm",
        artist="Artist",
        title="Track",
        album="Album",
        url="https://last.fm",
        template_slot=1,
        template_slots_total=1,
        ascii_beat=False,
        tryptych=False,
    )

    with patch("app.services.idle_service_governor.governed_service_active", return_value=True):
        with patch.object(db, "close"):
            with patch("app.workers.listening_relay_worker.SessionLocal", return_value=db):
                with patch(
                    "app.workers.listening_relay_worker.fetch_recent_track_lastfm_sync",
                    return_value=track,
                ):
                    with patch("app.workers.listening_relay_worker.relay_may_send_now", return_value=True):
                        with patch(
                            "app.workers.listening_relay_worker.build_relay_outbound",
                            return_value=outbound,
                        ):
                            with patch("app.workers.listening_relay_worker.queue_listening_relay_post") as queue_mock:
                                poll_listening_relay_lastfm()

    stored = db.query(ListeningRelaySettings).filter(ListeningRelaySettings.id == 1).one()
    assert stored.last_lastfm_signature == "new-sig"
    queue_mock.assert_called_once()


def test_post_listening_relay_marks_lock_busy_on_timeout(db):
    ch = Channel(id=1, name="Loot Room", identifier="@loot")
    db.add(ch)
    log = ListeningRelayPostLog(
        trigger_kind="test",
        status="queued",
        channel_id=1,
    )
    db.add(log)
    db.commit()

    async def _lock_timeout(timeout_s=None):
        raise TimeoutError("poster lock timed out")

    with patch("app.workers.poster_worker._begin_poster_async_task"):
        with patch("app.workers.poster_worker._reset_poster_client", new_callable=AsyncMock):
            with patch("app.workers.poster_worker._acquire_poster_session_lock", side_effect=_lock_timeout):
                with patch("app.workers.poster_worker._release_poster_session_lock", new_callable=AsyncMock):
                    with patch.object(db, "close"):
                        with patch("app.database.session.SessionLocal", return_value=db):
                            post_listening_relay_message(
                                1,
                                "<b>hi</b>",
                                relay_log_id=log.id,
                            )

    stored = db.query(ListeningRelayPostLog).filter(ListeningRelayPostLog.id == log.id).one()
    assert stored.status == "failed"
    assert stored.error_message == "lock_busy"
