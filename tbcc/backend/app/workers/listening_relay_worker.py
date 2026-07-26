import logging
from datetime import datetime, timedelta

from app.database.session import SessionLocal
from app.models.channel import Channel
from app.models.listening_relay_settings import ListeningRelaySettings
from app.services.listening_relay_compose import build_relay_outbound
from app.services.listening_relay_lastfm import fetch_recent_track_lastfm_sync
from app.services.listening_relay_admission import relay_may_send_now
from app.services.listening_relay_history import queue_listening_relay_post
from app.services.listening_relay_templates import get_template_variations_list
from app.services.listening_relay_target import (
    relay_has_send_target,
    relay_random_network_enabled,
    resolve_listening_relay_send_target,
)
from app.workers.celery_app import celery

logger = logging.getLogger(__name__)

ROW_ID = 1


def _ensure_row(db) -> ListeningRelaySettings:
    r = db.query(ListeningRelaySettings).filter(ListeningRelaySettings.id == ROW_ID).first()
    if r:
        return r
    r = ListeningRelaySettings(id=ROW_ID)
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


@celery.task(name="app.workers.listening_relay_worker.poll_listening_relay_lastfm")
def poll_listening_relay_lastfm():
    from app.services.idle_service_governor import governed_service_active

    if not governed_service_active("listening_relay"):
        return {"ok": True, "skipped": "governed_idle"}

    db = SessionLocal()
    try:
        row = _ensure_row(db)
        if not row.enabled or not relay_has_send_target(row):
            return
        user = (row.lastfm_username or "").strip()
        key = (row.lastfm_api_key or "").strip()
        if not user or not key:
            return
        interval = max(1, int(row.poll_interval_minutes or 3))
        now = datetime.utcnow()
        if row.last_poll_at and (now - row.last_poll_at) < timedelta(minutes=interval):
            return

        track = fetch_recent_track_lastfm_sync(username=user, api_key=key)
        row.last_poll_at = now
        if not track:
            db.commit()
            return

        n_templates = len(get_template_variations_list(row))

        sig = track.get("signature") or ""
        channel_id, thread_id = resolve_listening_relay_send_target(db, row)
        if not channel_id:
            logger.warning("listening relay: could not resolve send target")
            db.commit()
            return
        ch = db.query(Channel).filter(Channel.id == channel_id).first()
        if not ch:
            logger.warning("listening relay: channel %s missing", channel_id)
            db.commit()
            return

        if not sig:
            db.commit()
            return

        if row.last_lastfm_signature is None:
            row.last_lastfm_signature = sig
            db.commit()
            return

        if row.last_lastfm_signature == sig:
            db.commit()
            return

        if not relay_may_send_now(db):
            db.commit()
            return {"ok": True, "skipped": "scheduler_overdue"}

        outbound = build_relay_outbound(
            row,
            artist=track.get("artist") or "",
            title=track.get("title") or "",
            album=track.get("album"),
            url=track.get("url"),
            source="lastfm",
            source_label="Last.fm",
            consume=True,
            db=db,
        )
        logger.info(
            "listening relay Last.fm post channel=%s thread=%s random=%s template_slots=%s copy_followups=%s ascii=%s tryptych=%s",
            channel_id,
            thread_id,
            relay_random_network_enabled(row),
            n_templates,
            len(outbound.copy_followups),
            outbound.ascii_beat,
            outbound.tryptych,
        )
        row.last_lastfm_signature = sig
        queue_listening_relay_post(
            db,
            trigger="lastfm",
            channel_id=int(channel_id),
            message_thread_id=thread_id,
            random_lane=relay_random_network_enabled(row),
            outbound=outbound,
            send_silent=bool(row.send_silent),
            extra={"lastfm_signature": sig},
        )
        db.commit()
        logger.info("listening relay: queued Last.fm post for channel %s", channel_id)
    except Exception:
        logger.exception("poll_listening_relay_lastfm failed")
        try:
            db.rollback()
        except Exception:
            pass
    finally:
        db.close()


@celery.task(name="app.workers.listening_relay_worker.post_listening_relay_bot_api")
def post_listening_relay_bot_api(
    channel_id: int,
    html_body: str,
    message_thread_id: int | None = None,
    send_silent: bool = True,
    copy_followups_json: str | None = None,
    relay_log_id: int | None = None,
):
    """Bot API relay send — ops_relay queue, no Telethon poster lock."""
    from app.services.listening_relay_bot_send import send_listening_relay_via_bot_api
    from app.services.listening_relay_history import mark_relay_post_failed, mark_relay_post_sent

    db = SessionLocal()
    try:
        out = send_listening_relay_via_bot_api(
            db,
            channel_id=int(channel_id),
            html_body=html_body,
            message_thread_id=message_thread_id,
            send_silent=bool(send_silent),
            copy_followups_json=copy_followups_json,
        )
        if relay_log_id:
            if out.get("ok"):
                mark_relay_post_sent(
                    db,
                    int(relay_log_id),
                    telegram_message_id=out.get("message_id"),
                )
            else:
                mark_relay_post_failed(db, int(relay_log_id), str(out.get("error") or "bot_api_failed"))
            db.commit()
        if not out.get("ok"):
            logger.warning(
                "post_listening_relay_bot_api failed channel_id=%s: %s",
                channel_id,
                out.get("error"),
            )
    except Exception as e:
        logger.exception("post_listening_relay_bot_api failed channel_id=%s", channel_id)
        if relay_log_id:
            try:
                mark_relay_post_failed(db, int(relay_log_id), str(e))
                db.commit()
            except Exception:
                db.rollback()
    finally:
        db.close()


@celery.task(name="app.workers.listening_relay_worker.listening_relay_social_fanout")
def listening_relay_social_fanout(
    html_body: str,
    copy_block_followup_html: str | None = None,
    relay_log_id: int | None = None,
):
    from app.services.listening_relay_social import run_listening_relay_social_fanout

    run_listening_relay_social_fanout(html_body, copy_block_followup_html, relay_log_id=relay_log_id)
