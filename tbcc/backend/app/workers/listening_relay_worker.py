import logging
from datetime import datetime, timedelta

from app.database.session import SessionLocal
from app.models.channel import Channel
from app.models.listening_relay_settings import ListeningRelaySettings
from app.services.listening_relay_compose import build_relay_outbound
from app.services.listening_relay_lastfm import fetch_recent_track_lastfm_sync
from app.services.listening_relay_send import followups_to_json
from app.services.listening_relay_templates import get_template_variations_list
from app.workers.celery_app import celery
from app.workers.poster_worker import post_listening_relay_message

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
        if not row.enabled or not row.channel_id:
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
        ch = db.query(Channel).filter(Channel.id == row.channel_id).first()
        if not ch:
            logger.warning("listening relay: channel %s missing", row.channel_id)
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

        outbound = build_relay_outbound(
            row,
            artist=track.get("artist") or "",
            title=track.get("title") or "",
            album=track.get("album"),
            url=track.get("url"),
            source="lastfm",
            source_label="Last.fm",
            consume=True,
        )
        logger.info(
            "listening relay Last.fm post channel=%s template_slots=%s copy_followups=%s ascii=%s tryptych=%s",
            row.channel_id,
            n_templates,
            len(outbound.copy_followups),
            outbound.ascii_beat,
            outbound.tryptych,
        )
        row.last_lastfm_signature = sig
        db.commit()
        followups_json = followups_to_json(outbound.copy_followups)
        post_listening_relay_message.delay(
            int(row.channel_id),
            outbound.main_html,
            row.message_thread_id,
            bool(row.send_silent),
            None,
            followups_json,
        )
        listening_relay_social_fanout.delay(outbound.main_html, followups_json)
        logger.info("listening relay: queued Last.fm post for channel %s", row.channel_id)
    except Exception:
        logger.exception("poll_listening_relay_lastfm failed")
        try:
            db.rollback()
        except Exception:
            pass
    finally:
        db.close()


@celery.task(name="app.workers.listening_relay_worker.listening_relay_social_fanout")
def listening_relay_social_fanout(html_body: str, copy_block_followup_html: str | None = None):
    from app.services.listening_relay_social import run_listening_relay_social_fanout

    run_listening_relay_social_fanout(html_body, copy_block_followup_html)
